from flask import Flask, request, jsonify, render_template
import json, os

app = Flask(__name__)
DATA_FILE = '/content/drive/MyDrive/escola_app/escola_data.json'

def load():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"alunos": {}, "materias": {}}

def save(dados):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/dados")
def get_dados():
    return jsonify(load())

@app.route("/api/alunos", methods=["POST"])
def add_aluno():
    d = load()
    body = request.json
    mat, nome = body.get("matricula","").strip(), body.get("nome","").strip()
    if not mat or not nome:
        return jsonify({"erro": "Matricula e nome sao obrigatorios."}), 400
    if mat in d["alunos"]:
        return jsonify({"erro": "Matricula ja cadastrada."}), 400
    d["alunos"][mat] = {"nome": nome, "materias": []}
    save(d)
    return jsonify({"ok": True})

@app.route("/api/alunos/<matricula>", methods=["DELETE"])
def del_aluno(matricula):
    d = load()
    if matricula not in d["alunos"]:
        return jsonify({"erro": "Aluno nao encontrado."}), 404
    del d["alunos"][matricula]
    for mat in d["materias"].values():
        mat.get("chamadas", {}).pop(matricula, None)
        mat.get("notas", {}).pop(matricula, None)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/alunos/<matricula>/materias", methods=["POST"])
def assoc_materia(matricula):
    d = load()
    materia = request.json.get("materia","").strip()
    if matricula not in d["alunos"]:
        return jsonify({"erro": "Aluno nao encontrado."}), 404
    if materia not in d["materias"]:
        return jsonify({"erro": "Materia nao encontrada."}), 404
    aluno = d["alunos"][matricula]
    if materia not in aluno["materias"]:
        aluno["materias"].append(materia)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/alunos/<matricula>/materias/<materia>", methods=["DELETE"])
def desassoc_materia(matricula, materia):
    d = load()
    aluno = d["alunos"].get(matricula)
    if aluno and materia in aluno["materias"]:
        aluno["materias"].remove(materia)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/materias", methods=["POST"])
def add_materia():
    d = load()
    body = request.json
    nome = body.get("nome","").strip()
    prof = body.get("professor","").strip()
    if not nome:
        return jsonify({"erro": "Nome da materia e obrigatorio."}), 400
    if nome in d["materias"]:
        return jsonify({"erro": "Materia ja existe."}), 400
    d["materias"][nome] = {"professor": prof, "chamadas": {}, "notas": {}}
    save(d)
    return jsonify({"ok": True})

@app.route("/api/materias/<nome>", methods=["DELETE"])
def del_materia(nome):
    d = load()
    if nome not in d["materias"]:
        return jsonify({"erro": "Materia nao encontrada."}), 404
    del d["materias"][nome]
    for aluno in d["alunos"].values():
        if nome in aluno.get("materias", []):
            aluno["materias"].remove(nome)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/chamada", methods=["POST"])
def salvar_chamada():
    d = load()
    body = request.json
    materia = body.get("materia","").strip()
    data    = body.get("data","").strip()
    presencas = body.get("presencas", {})
    if materia not in d["materias"]:
        return jsonify({"erro": "Materia nao encontrada."}), 404
    chamadas = d["materias"][materia].setdefault("chamadas", {})
    for mat, presente in presencas.items():
        chamadas.setdefault(mat, {})[data] = bool(presente)
    save(d)
    return jsonify({"ok": True})

@app.route("/api/notas", methods=["POST"])
def salvar_notas():
    d = load()
    body    = request.json
    materia = body.get("materia","").strip()
    aval    = body.get("avaliacao","").strip()
    notas   = body.get("notas", {})
    if materia not in d["materias"]:
        return jsonify({"erro": "Materia nao encontrada."}), 404
    reg = d["materias"][materia].setdefault("notas", {})
    for mat, val in notas.items():
        try:
            n = float(str(val).replace(",","."))
            if not (0 <= n <= 10):
                raise ValueError
            reg.setdefault(mat, {})[aval] = n
        except (ValueError, TypeError):
            pass
    save(d)
    return jsonify({"ok": True})
