from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os, html, psycopg2, sqlite3, json, uuid
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave")
SENHA = os.environ.get("APP_SENHA", "escola1234")
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    if DATABASE_URL:
        return psycopg2.connect(DATABASE_URL)
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escola_local.db")
    return sqlite3.connect(db_path)

def init_db():
    conn = get_conn()
    c = conn.cursor()
    try:
        if DATABASE_URL:
            c.execute("""
                CREATE TABLE IF NOT EXISTS dados (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    conteudo JSONB NOT NULL
                )
            """)
            c.execute("""
                INSERT INTO dados (id, conteudo)
                VALUES (1, '{"alunos": {}, "materias": {}}')
                ON CONFLICT (id) DO NOTHING
            """)
        else:
            c.execute("""
                CREATE TABLE IF NOT EXISTS dados (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    conteudo TEXT NOT NULL
                )
            """)
            c.execute("""
                INSERT OR IGNORE INTO dados (id, conteudo)
                VALUES (1, '{"alunos": {}, "materias": {}}')
            """)
        conn.commit()
    finally:
        c.close()
        conn.close()

def load():
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("SELECT conteudo FROM dados WHERE id = 1")
        row = c.fetchone()
        if not row:
            return {"alunos": {}, "materias": {}}
        val = row[0]
        if isinstance(val, str):
            return json.loads(val)
        return val
    finally:
        c.close()
        conn.close()

def save(dados):
    placeholder = "%s" if DATABASE_URL else "?"
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(f"UPDATE dados SET conteudo = {placeholder} WHERE id = 1", [json.dumps(dados)])
        conn.commit()
    finally:
        c.close()
        conn.close()

def sanitize(text):
    return html.escape(str(text).strip())[:100]

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logado"):
            return jsonify({"erro": "Não autorizado."}), 401
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = ""
    if request.method == "POST":
        if request.form.get("senha", "") == SENHA:
            session["logado"] = True
            return redirect(url_for("index"))
        erro = "Senha incorreta."
    return render_template("login.html", erro=erro)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def index():
    if not session.get("logado"):
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/api/dados")
@login_required
def get_dados():
    return jsonify(load())

@app.route("/api/alunos", methods=["POST"])
@login_required
def add_aluno():
    d = load()
    body = request.json
    nome = sanitize(body.get("nome", ""))
    if not nome:
        return jsonify({"erro": "Nome é obrigatório."}), 400
    if any(a["nome"].lower() == nome.lower() for a in d["alunos"].values()):
        return jsonify({"erro": "Aluno já cadastrado."}), 400
    mat = str(uuid.uuid4())[:8]
    while mat in d["alunos"]:
        mat = str(uuid.uuid4())[:8]
    d["alunos"][mat] = {"nome": nome, "materias": []}
    save(d)
    return jsonify({"ok": True})

@app.route("/api/alunos/<matricula>", methods=["DELETE"])
@login_required
def del_aluno(matricula):
    d = load()
    matricula = sanitize(matricula)
    if matricula not in d["alunos"]:
        return jsonify({"erro": "Aluno não encontrado."}), 404
    del d["alunos"][matricula]
    for mat in d["materias"].values():
        mat.get("chamadas", {}).pop(matricula, None)
        mat.get("notas", {}).pop(matricula, None)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/alunos/<matricula>", methods=["PUT"])
@login_required
def edit_aluno(matricula):
    d = load()
    matricula = sanitize(matricula)
    if matricula not in d["alunos"]:
        return jsonify({"erro": "Aluno não encontrado."}), 404
    nome = sanitize(request.json.get("nome", ""))
    if not nome:
        return jsonify({"erro": "Nome é obrigatório."}), 400
    if any(a["nome"].lower() == nome.lower() and k != matricula for k, a in d["alunos"].items()):
        return jsonify({"erro": "Já existe um aluno com esse nome."}), 400
    d["alunos"][matricula]["nome"] = nome
    save(d)
    return jsonify({"ok": True})

@app.route("/api/alunos/<matricula>/materias", methods=["POST"])
@login_required
def assoc_materia(matricula):
    d = load()
    matricula = sanitize(matricula)
    materia = sanitize(request.json.get("materia", ""))
    if matricula not in d["alunos"]:
        return jsonify({"erro": "Aluno não encontrado."}), 404
    if materia not in d["materias"]:
        return jsonify({"erro": "Matéria não encontrada."}), 404
    aluno = d["alunos"][matricula]
    if materia not in aluno["materias"]:
        aluno["materias"].append(materia)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/alunos/<matricula>/materias/<materia>", methods=["DELETE"])
@login_required
def desassoc_materia(matricula, materia):
    d = load()
    aluno = d["alunos"].get(sanitize(matricula))
    materia = sanitize(materia)
    if aluno and materia in aluno["materias"]:
        aluno["materias"].remove(materia)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/materias", methods=["POST"])
@login_required
def add_materia():
    d = load()
    nome = sanitize(request.json.get("nome", ""))
    prof = sanitize(request.json.get("professor", ""))
    if not nome:
        return jsonify({"erro": "Nome da matéria é obrigatório."}), 400
    if nome in d["materias"]:
        return jsonify({"erro": "Matéria já existe."}), 400
    d["materias"][nome] = {"professor": prof, "chamadas": {}, "notas": {}}
    save(d)
    return jsonify({"ok": True})

@app.route("/api/materias/<nome>", methods=["DELETE"])
@login_required
def del_materia(nome):
    d = load()
    nome = sanitize(nome)
    if nome not in d["materias"]:
        return jsonify({"erro": "Matéria não encontrada."}), 404
    del d["materias"][nome]
    for aluno in d["alunos"].values():
        if nome in aluno.get("materias", []):
            aluno["materias"].remove(nome)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/chamada", methods=["POST"])
@login_required
def salvar_chamada():
    d = load()
    body = request.json
    materia = sanitize(body.get("materia", ""))
    data = sanitize(body.get("data", ""))
    presencas = body.get("presencas", {})
    if materia not in d["materias"]:
        return jsonify({"erro": "Matéria não encontrada."}), 404
    chamadas = d["materias"][materia].setdefault("chamadas", {})
    for mat, presente in presencas.items():
        chamadas.setdefault(sanitize(mat), {})[data] = bool(presente)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/notas", methods=["POST"])
@login_required
def salvar_notas():
    d = load()
    body = request.json
    materia = sanitize(body.get("materia", ""))
    if materia not in d["materias"]:
        return jsonify({"erro": "Matéria não encontrada."}), 404
    
    input_notas = body.get("notas", {})
    if not isinstance(input_notas, dict):
        return jsonify({"erro": "Dados inválidos."}), 400
        
    sanitized_notas = {}
    for mat_aluno, evals in input_notas.items():
        mat_aluno = sanitize(mat_aluno)
        if mat_aluno not in d["alunos"]:
            continue
        if not isinstance(evals, dict):
            continue
            
        aluno_grades = {}
        for aval, val in evals.items():
            aval = sanitize(aval)
            if not aval:
                continue
            if val is None or val == "":
                continue
            try:
                n = float(str(val).replace(",", "."))
                if 0 <= n <= 10:
                    aluno_grades[aval] = n
            except (ValueError, TypeError):
                pass
        if aluno_grades:
            sanitized_notas[mat_aluno] = aluno_grades
            
    d["materias"][materia]["notas"] = sanitized_notas
    save(d)
    return jsonify({"ok": True})

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, port=port)
