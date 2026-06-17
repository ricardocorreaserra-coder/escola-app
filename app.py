from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import os, html, psycopg2, json, uuid
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave")
SENHA = os.environ.get("APP_SENHA", "escola1234")
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as c:
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
            conn.commit()

def load():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("SELECT conteudo FROM dados WHERE id = 1")
            row = c.fetchone()
            return row[0] if row else {"alunos": {}, "materias": {}}

def save(dados):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("UPDATE dados SET conteudo = %s WHERE id = 1", [json.dumps(dados)])
            conn.commit()

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
    aval = sanitize(body.get("avaliacao", ""))
    notas = body.get("notas", {})
    if materia not in d["materias"]:
        return jsonify({"erro": "Matéria não encontrada."}), 404
    reg = d["materias"][materia].setdefault("notas", {})
    for mat, val in notas.items():
        try:
            n = float(str(val).replace(",", "."))
            if not (0 <= n <= 10):
                raise ValueError
            reg.setdefault(sanitize(mat), {})[aval] = n
        except (ValueError, TypeError):
            pass
    save(d)
    return jsonify({"ok": True})

init_db()

if __name__ == "__main__":
    app.run(debug=False, port=5000)
