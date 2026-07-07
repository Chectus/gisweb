from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_laboratory_gis'

USERS = {
    'admin': 'secret',
    'sanya': 'kectus',
    'luchik': 'aboba'
}

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('hub'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USERS and USERS[username] == password:
            session['user'] = username
            return redirect(url_for('hub'))
        else:
            return render_template('login.html', error='Неверный логин или пароль')
            
    return render_template('login.html')

@app.route('/hub')
def hub():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('hub.html', username=session['user'])

@app.route('/map')
def map_page():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('map.html')

@app.route('/docs')
def docs():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('docs.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)