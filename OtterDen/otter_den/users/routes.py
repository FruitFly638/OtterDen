# Copyright ByteOtter (c) 2021-2022

from flask import current_app, render_template, url_for, abort, flash, redirect, request, Blueprint
from flask_login import login_user, current_user, logout_user, login_required
from otter_den import db, bcrypt
from otter_den.models import User, Post
from otter_den.users.forms import RegistrationForm, LoginForm, UpdateAccountInfoForm, RequestPasswordResetForm, ResetPasswordForm
from otter_den.users.utils import save_picture, send_reset_email
from otter_den.posts.utils import delete_from_db

import os

users = Blueprint('users', __name__)


@users.route("/register", methods = ['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = RegistrationForm()
    #displays flash message when form validates successfully & redirects user to home page
    if form.validate_on_submit():
        #hash user pw and decode it into a string to be saved in the database
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash(f'Your Account has been created! Welcome, {form.username.data}!', 'success')
        return redirect(url_for('users.login'))
    return render_template('register.html', title = 'Register', form = form)


@users.route("/login", methods = ['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            flash(f'Welcome, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(url_for('main.home')) #use static redirect to home page after login
        elif user == None:
            flash('Sorry, there is no user registered with this mail address.', 'danger')
        else:
            flash('Login unsuccessful. Please check your email and password.', 'danger')
    return render_template('login.html', title = 'Login', form = form)


@users.route("/logout")
def logout():
    logout_user()
    flash('Goodbye, See you next time!', 'success')
    return redirect(url_for('main.home'))


@users.route("/account", methods = ['GET', 'POST'])
#require login to access account page
@login_required
def account():
    form = UpdateAccountInfoForm()
    #if form is valid on submit. Update the account information
    if form.validate_on_submit():
        if form.picture.data:
            #if a picture file is given AND the current picture file is NOT default -> remove the old file
            if current_user.image_file != 'default.jpg' and current_user.image_file != None:
                os.remove(os.path.join(current_app.root_path, 'static/profile_pictures', current_user.image_file))
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.biography = form.biography.data
        db.session.commit()
        flash('Your account information has been updated!', 'success')
        return redirect(url_for('users.account'))
    #populate form with current username and email
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.biography.data = current_user.biography
    #set user profile picture as default.jpg when none is uploaded and pass to account template
    image_file = url_for('static', filename = 'profile_pictures/' + current_user.image_file)
    return render_template('account.html', title = 'My Account', image_file = image_file, form = form)


@users.route("/account/delete", methods = ['GET', 'POST'])
@login_required
def delete_user():
    username = current_user.username
    user = User.query.filter_by(username = username).first_or_404()
    #only the current user should be able to delete their own profile
    if user.username != username:
        abort(403) #forbidden
    if user.image_file != 'default.jpg':
        os.remove(os.path.join(current_app.root_path, 'static/profile_pictures', user.image_file))
    purge_posts(username) #TODO
    db.session.delete(user)
    db.session.commit()
    flash('Your account has been deleted. We will miss you!', 'success')
    return redirect(url_for('main.home'))

#show complete user profile and a post history underneath
@users.route("/user/history/<string:username>")
def show_user_post_history(username):
    page = request.args.get('page', 1, type = int)
    user = User.query.filter_by(username = username).first_or_404()
    posts = Post.query.filter_by(author=user).order_by(Post.date_posted.desc()).paginate(page = page, per_page = 10)
    return render_template('post_history.html', title = 'History - ' + user.username, posts = posts, user = user)

@users.route("/reset_password", methods = ['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = RequestPasswordResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email = form.email.data).first()
        send_reset_email(user)
        flash('An email with instructions for resetting your password has been sent to your email account!', 'info')
        return redirect(url_for('users.login'))
    return render_template('reset_password_request.html', title = 'Reset Password', form = form)


@users.route("/reset_password/<token>", methods = ['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('The token is inavlid or expired!', 'warning')
        return redirect(url_for('users.reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        #hash user pw and decode it into a string to be saved in the database
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_pw
        db.session.commit()
        flash(f'Your password has been changed! You are now able to login!', 'success')
        return redirect(url_for('users.login'))
    return render_template('reset_token.html', title = 'Reset Password', form = form)


@users.route("/user/<string:username>", methods = ['GET'])
def user_profile(username):
    user = User.query.filter_by(username = username).first_or_404()
    return render_template('user_profile.html', title = 'Profile - ' + user.username, user = user)


@users.route("/user/<string:username>/purge_posts", methods = ['POST'])
@login_required
def purge_posts(username):
    user = User.query.filter_by(username = username).first_or_404()
    post_ids_to_delete = []
    for post in user.posts:
        post_ids_to_delete += [post.id]
    for post_id in post_ids_to_delete:
        delete_from_db(post_id, send_flash = False)
    db.session.commit()
    page = request.args.get('page', 1, type = int)
    posts = Post.query.filter_by(author=user).order_by(Post.date_posted.desc()).paginate(page = page, per_page = 10)
    flash('Your posts have been PURGED!', 'warning')
    return render_template('post_history.html', title = 'History of {user.username}', posts = posts, user = user)
