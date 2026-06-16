from flask import Flask, request, jsonify, render_template, session, redirect, url_for
import json, os, html

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-secret")

SENHA = os.environ.get("APP_SENHA", "escola1234")
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escola_data.json")

def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"alunos": {}, "materias": {}}

def save(dados):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def sanitize(text):
    return html.escape(str(text).strip())[:100]

def login_required(f):
    from functools import wraps
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
        senha = request.form.get("senha", "")
        if senha == SENHA:
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
    mat = sanitize(body.get("matricula", ""))
    nome = sanitize(body.get("nome", ""))
    if not mat or not nome:
        return jsonify({"erro": "Matricula e nome são obrigatórios."}), 400
    if mat in d["alunos"]:
        return jsonify({"erro": "Matrícula já cadastrada."}), 400
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

if __name__ == "__main__":
    app.run(debug=False, port=5000)
