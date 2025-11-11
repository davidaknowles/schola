#!/usr/bin/env python3
from flask import Flask, request, render_template, redirect, url_for
from fetch_author_publications import fetch_author_publications, compute_imputed_metrics

app = Flask(__name__)

HOME_TEMPLATE = """
<!DOCTYPE html>
<html lang='en'>
<head>
  <meta charset='UTF-8'>
  <title>Scholar Explorer</title>
  <style>
    body {font-family: -apple-system, BlinkMacSystemFont, Arial; max-width: 900px; margin:40px auto; padding:0 20px; background:#fafafa;}
    h1 {margin-top:0;}
    form {background:#fff; padding:20px; border-radius:8px; box-shadow:0 2px 4px rgba(0,0,0,.1);} 
    label {display:block; font-weight:600; margin-bottom:6px;}
    input[type=text], input[type=email] {width:100%; padding:10px; border:1px solid #ccc; border-radius:4px; font-size:16px;}
    .row {margin-bottom:15px;}
    button {background:#0066cc; color:#fff; border:none; padding:12px 20px; font-size:16px; border-radius:6px; cursor:pointer;}
    button:hover {background:#004f99;}
    .footer {margin-top:40px; font-size:12px; color:#666;}
  </style>
</head>
<body>
  <h1>Scholar Explorer</h1>
  <form method='GET' action='{{ url_for('results') }}'>
    <div class='row'>
      <label for='author'>Author (e.g., Knowles DA)</label>
      <input id='author' name='author' type='text' required placeholder='LastName Initials' value='{{ request.args.get('author','') }}'>
    </div>
    <div class='row'>
      <label for='email'>Email (for Entrez)</label>
      <input id='email' name='email' type='email' placeholder='you@example.com' value='{{ request.args.get('email','') }}'>
    </div>
    <div class='row'>
      <label for='start_year'>Start Year (optional)</label>
      <input id='start_year' name='start_year' type='text' pattern='[0-9]{4}' placeholder='2018' value='{{ request.args.get('start_year','') }}'>
    </div>
    <div class='row'>
      <label for='end_year'>End Year (optional)</label>
      <input id='end_year' name='end_year' type='text' pattern='[0-9]{4}' placeholder='2025' value='{{ request.args.get('end_year','') }}'>
    </div>
    <button type='submit'>Fetch Publications</button>
  </form>
  <div class='footer'>Data from PubMed & NIH iCite. RCR may be imputed when missing.</div>
</body>
</html>
"""

@app.route('/')
def home():
  return render_template('index.html')

@app.route('/results')
def results():
    author = request.args.get('author', '').strip()
    email = request.args.get('email', '') or 'example@example.com'
    start_year = request.args.get('start_year', '').strip() or None
    end_year = request.args.get('end_year', '').strip() or None
    filter_position = request.args.get('filter_position', '1') == '1'

    if not author:
        return redirect(url_for('home'))

    try:
        pubs = fetch_author_publications(
            author_name=author,
            email=email,
            start_year=int(start_year) if start_year else None,
            end_year=int(end_year) if end_year else None,
            output_format='html',
            filter_author_position=filter_position
        )
        compute_imputed_metrics(pubs)
    except Exception as e:
        return render_template('base.html', content=f"<p>Error fetching publications: {e}</p>")

    return render_template('results.html', publications=pubs, author_name=author)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
