import datetime
import os
import re
import secrets
from PIL import Image
from flask import render_template, url_for, flash, redirect, request, abort
from flask_wtf.file import FileField, FileAllowed
from flask_login import login_user, current_user, logout_user, login_required
from flask_mail import Message
from sqlalchemy import or_
from bookapp.forms import RegistrationForm, LoginForm, PostForm, UpdateAccountForm, RequestResetForm, ResetPasswordForm, CommentForm, SearchForm
from bookapp.models import User, Posts, Saves, Comments, Notifications
from bookapp import app, db, bcrypt, mail
from bookapp.scrape import getBookDetails

@app.route('/')
@app.route('/home')
def index():
    #search = request.args.get('search', None, type=str)
    page = request.args.get('page', 1, type=int)
    
    
    posts = Posts.query.order_by(Posts.date_posted.desc()).paginate(per_page=5, page=page)
    return render_template('home.html', posts=posts)

@app.route('/search', methods=["GET", "POST"])
def search():
    form = SearchForm()
    page = request.args.get('page', 1, type=int)
    if form.validate_on_submit():
        if not re.search(r'[^0-9^x^X]', str(form.search.data)):
            posts = Posts.query.filter(Posts.isbn.ilike(search)).order_by(Posts.date_posted.desc()).paginate(per_page=5, page=page)
        else:
            search = '%'.join(a for a in form.search.data)
            posts = Posts.query.filter(or_(Posts.title.contains(search), Posts.writers.contains(search))).order_by(Posts.date_posted.desc()).paginate(per_page=5, page=page)
    else:
        posts = Posts.query.order_by(Posts.date_posted.desc()).paginate(per_page=5, page=page)
    if not posts:
        flash(f'No books found')
    return render_template('search.html', posts=posts, title="Search", form=form)

@app.route('/user/<username>')
def user_post(username):
    user = User.query.filter_by(username=username).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = Posts.query\
                 .filter_by(author=user)\
                 .paginate(per_page=5, page=page)
    return render_template('home.html', title=f"{username} Posts", posts=posts)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/register', methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data.lower(), password=hashed_password, email=form.email.data.lower(),
                    major=form.major.data, payment_profile=form.payment_profile.data)
        db.session.add(user)
        db.session.commit()
        flash(f'Your account has been created! Please log in', category='Success')
        return redirect(url_for('login'))
    return render_template('register.html', title="Register", form=form)

@app.route('/login', methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash(f'Login failed, please check email and password')
    return render_template('login.html', title="Login", form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/account', methods=["GET", "POST"])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
            current_user.image_file = picture_file
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.major = form.major.data
        current_user.payment_profile = form.payment_profile.data
        db.session.commit()
        flash('Your account has been updated!', category='success')
        return redirect(url_for('account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.major.data = current_user.major
        form.picture.data = current_user.image_file
        form.payment_profile.data = current_user.payment_profile
    image_file = url_for('static', filename='profile_pics/' + current_user.image_file)
    return render_template('account.html', title="Account", image_file=image_file, form=form)    
    
def save_picture(form_picture):                                                                                           
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(app.root_path, 'static/profile_pics', picture_fn)
    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn
                          
def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Password Reset Request', 
                   sender='noreplyFORCLASS@my.unt.edu', 
                   recipients=[user.email])
    msg.body = f"""To reset your password, visit the following link:
                   {url_for('reset_token', token=token, _external=True)}
                   If you did not make this request, then simply record this email and no changes will be made."""
    mail.send(msg)
    
@app.route("/reset_password", methods=["GET", "POST"])
def reset_request():
    if current_user.is_authenticated:
        return redirect('/home')
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        send_reset_email(user)
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('login'))
    return render_template('reset_request.html', title='Reset Password',
                           form=form)
                          
@app.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect('/home')
    user = User.verify_reset_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('reset_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password = hashed_password
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('login'))
    return render_template('reset_token.html', title='Reset Password', form=form)                        
 
@app.route('/post/new', methods=["GET", "POST"])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        data = False
        if len(form.isbn.data) == 10 or len(form.isbn.data) == 13:
            data = getBookDetails(form.isbn.data)
        if data:
            post = Posts(isbn=form.isbn.data, condition=form.condition.data, price=form.price.data, major=form.major.data, author=current_user, title=data['title'], publisher=data['publisher'], writers=data['author'], image_ref=data['imgCover'])
            db.session.add(post)
            db.session.commit()
            flash("Your post has been created.", "success")
            return redirect(url_for('post', post_id=post.id))
        else:
            flash("There was an error fetching your textbook.\nPlease Check your ISBN", "warning")
            # return render_template('create_post.html', title="New Post", form=form, legend='New Post')
    return render_template('create_post.html', title="New Post", form=form, legend='New Post')






#route for manual entry of isbn, title, etc.
@app.route('/post/new/manual-entry', methods=["GET", "POST"])
@login_required
def new_manual_post():
    form = PostForm()
    
    if form.validate_on_submit():
        if form.title.data:
            #no scraping for manual entry
            #data = getBookDetails(form.isbn.data)
            #image_file = url_for('static', filename='profile_pics/book.jpg')

            post = Posts(isbn=form.isbn.data, condition=form.condition.data, price=form.price.data, major=form.major.data, author=current_user, title=form.title.data)
            
            db.session.add(post)
            db.session.commit()

            return redirect('/home')
        else:
            flash("Please Enter a Title", "warning")
        
    return render_template('create_manually.html', title="New Manual Post", form=form, legend='New Manual Post')


@app.route('/comments')
@login_required
def comments():
    comment = Comments.query.filter_by(user_id=current_user.id).all()
    comments = []
    for c in comment:
        comments.append({
            "username": current_user.username,
            "img": current_user.image_file,
            "comment_text": c.comment_text,
            "comment_time": c.comment_time.strftime("%m-%d-%Y %I:%M%p"), 
            "post_link": c.posts_id,
        })
    
    return render_template('comments.html', title="My Comments", comment=comments)

@app.route('/notifications')
@login_required
def notifications():
    notifs = Notifications.query.filter_by(user_id=current_user.id).order_by(Notifications.seen==False).all()
    for notif in notifs:
        notif.seen = True
    db.session.commit()
    ids = [n.comment_id for n in notifs]
    comment = Comments.query.filter(Comments.id.in_(ids)).all()
    ids = [item.user_id for item in comment]
    users = User.query.filter(User.id.in_(ids)).all()
    comments = []
    for c in comment:
        user = None
        for item in users:
            if item.id == c.user_id:
                user = item
                break
        if user:
            comments.append({
                "username": user.username,
                "img": user.image_file,
                "comment_text": c.comment_text,
                "comment_time": c.comment_time.strftime("%m-%d-%Y %I:%M%p"),
                "post_link": c.posts_id,
            })

    return render_template('comments.html', title="Notifications", comment=comments)


@app.route('/post/<int:post_id>', methods=['GET','POST'])
def post(post_id):
    post = Posts.query.get_or_404(post_id)
    comment = Comments.query.filter_by(posts_id=post.id).order_by(Comments.comment_time.desc()).all()
    ids = [item.user_id for item in comment]
    users = User.query.filter(User.id.in_(ids)).all()

    cform = CommentForm()

    if current_user.is_authenticated:
        
        is_saved = Saves.query.filter_by(user_id=current_user.id, posts_id=post_id).all()

        if is_saved:
            cform.save.label.text = 'Unsave'
        else:
            cform.save.label.text = 'Save'
    else:
            cform.save.label.text = None

    comments = []
    for c in comment:
        user = None
        for item in users:
            if item.id == c.user_id:
                user = item
                break
        if user:
            comments.append({
                "username": user.username,
                "img": user.image_file,
                "comment_text": c.comment_text,
                "id": c.id,
                "comment_time": c.comment_time.strftime("%m-%d-%Y %I:%M%p")
            })
    
    #cform.comment.data = "Enter text here"     

    if cform.validate_on_submit():
        if cform.save.data:
            if len(is_saved) == 0:
                save = Saves(user_id=current_user.id, posts_id=post_id)
                db.session.add(save)
                db.session.commit()
                flash('This post has been saved.', 'success')
                return redirect(url_for('post', post_id=post_id))
            else:
                db.session.delete(is_saved[0])
                db.session.commit()
                flash('This post has been removed from saves.')
                return redirect(url_for('post', post_id=post_id))        
        else:
            if cform.comment.data != "Enter text here":
                comment = Comments(comment_text=cform.comment.data, user_id=current_user.id, posts_id=post.id)
                db.session.add(comment)
                db.session.commit()
                user = detectUsername(cform.comment.data)
                print(user)
                if user:
                    notif_user = User.query.filter_by(username=user).first()
                    print(notif_user)
                    notif = Notifications(comment_id=comment.id, post_id=post_id, user_id=notif_user.id)
                else:
                    notif = Notifications(comment_id=comment.id, post_id=post_id, user_id=post.author.id)
                db.session.add(notif)
                db.session.commit()
                flash("Your comment was posted successfully!", "success")
                
                #post.comments.data = post.comments.data + 1
                #push notification to user


                return redirect(url_for('post', post_id=post.id))
   
    return render_template('post.html', title=Posts.title, post=post, form=cform, comment=comments)


def detectUsername(comment):
    if "@" in comment:
        li = comment.split()
        for item in li:
            if "@" in item:
                item = item.strip("@,.?!")
                return item
            else:
                continue
    return None


def notification_truth():
    if current_user.is_authenticated:
        n = Notifications.query.filter_by(user_id=current_user.id, seen=False).all()
        if n:
            return True
    return False


app.jinja_env.globals.update(notification_truth=notification_truth)

@app.route('/posts/saves', methods=['GET', 'POST'])
@login_required
def saved():
    saves = Saves.query.filter_by(user_id=current_user.id).all()
    page = request.args.get('page', 1, type=int)
    ids = [item.posts_id for item in saves]
    post = Posts.query\
                 .filter(Posts.id.in_(ids))\
                 .paginate(per_page=5, page=page)
    
    # I will add something to where you can remove from saves
    return render_template('home.html', posts=post)


@app.route('/post/<int:post_id>/update', methods=['GET', 'POST'])
@login_required
def update_post(post_id):
    post = Posts.query.get_or_404(post_id)
    if post.author != current_user:
        abort(403)
    form = PostForm()
    if form.validate_on_submit():
        post.title = form.title.data
        post.condition = form.condition.data
        post.price = form.price.data
        post.major = form.major.data
        db.session.commit()
        flash("Your post was updated successfully!", "success")
        return redirect(url_for('post', post_id=post.id))
    elif request.method == 'GET':
        form.title.data = post.title
        form.isbn.data = post.isbn
        form.price.data = post.price
        form.major.data = post.major
        form.condition.data = post.condition
    return render_template('create_manually.html', title="Update Post", form=form)


@app.route('/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_post(post_id):
    post = Posts.query.get_or_404(post_id)
    comments = Comments.query.filter_by(posts_id=post.id).all()
    saves = Saves.query.filter_by(posts_id=post.id).all()
    if post.author != current_user:
        abort(403)
        
    # delete comments
    for c in comments:
        notif = Notifications.query.filter_by(comment_id=c.id).all()
        for n in notif:
            db.session.delete(n)
        db.session.delete(c)

    for s in saves:
        db.session.delete(s)

    # delete posts
    db.session.delete(post)
    db.session.commit()
    flash("Your post has been deleted", "success")
    return redirect('/home')

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comments.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        abort(403)
    post = request.args.get('post', type=int)

    # delete comments
    notif = Notifications.query.filter_by(comment_id=comment_id).all()
    for n in notif:
        db.session.delete(n)
    db.session.delete(comment)
    db.session.commit()
    flash("Your comment has been deleted", "success")
    return redirect(url_for('post', post_id=post))