from flask import Flask, request, jsonify, render_template, session, redirect, url_for

import os, html, psycopg2, sqlite3, json, uuid, time

from functools import wraps

from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave")

SENHA = os.environ.get("APP_SENHA", "escola1234")

DATABASE_URL = os.environ.get("DATABASE_URL")

# Configurações de cookies de sessão seguros

app.config.update(

SESSION_COOKIE_SECURE=DATABASE_URL is not None,

SESSION_COOKIE_HTTPONLY=True,

SESSION_COOKIE_SAMESITE='Lax',

)

# Limitador de tentativas de login por IP (Anti-Brute Force)

LOGIN_LIMIT = 5

BLOCK_TIME = 300  # 5 minutos

failed_attempts = {}  # ip -> {"count": int, "blocked_until": float}


def check_rate_limit(ip):

    now = time.time()

    if ip in failed_attempts:

        record = failed_attempts[ip]

        if record["blocked_until"] > now:

            remaining = int(record["blocked_until"] - now)

            return False, f"Muitas tentativas falhas. Tente novamente em {remaining} segundos."

        elif record["count"] >= LOGIN_LIMIT:

            failed_attempts[ip] = {"count": 0, "blocked_until": 0.0}

    return True, ""


def register_login_failure(ip):

    now = time.time()

    if ip not in failed_attempts:

        failed_attempts[ip] = {"count": 0, "blocked_until": 0.0}

    failed_attempts[ip]["count"] += 1

    if failed_attempts[ip]["count"] >= LOGIN_LIMIT:

        failed_attempts[ip]["blocked_until"] = now + BLOCK_TIME


def reset_login_attempts(ip):

    if ip in failed_attempts:

        del failed_attempts[ip]


# Cabeçalhos de Segurança HTTP

@app.after_request

def add_security_headers(response):

    response.headers['X-Frame-Options'] = 'DENY'

    response.headers['X-Content-Type-Options'] = 'nosniff'

    response.headers['X-XSS-Protection'] = '1; mode=block'

    response.headers['Content-Security-Policy'] = (

        "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com https://cdn.jsdelivr.net; "

        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "

        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "

        "img-src 'self' data:;"

    )

    return response


def get_conn():

    if DATABASE_URL:

        return psycopg2.connect(DATABASE_URL)

    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "escola_local.db")

    return sqlite3.connect(db_path)


def bootstrap_admin():

    d = load()

    if "usuarios" not in d:

        d["usuarios"] = {}

    if not d["usuarios"]:

        admin_pass = os.environ.get("APP_SENHA", "escola1234")

        d["usuarios"]["admin"] = {

            "usuario": "admin",

            "nome": "Administrador",

            "senha_hash": generate_password_hash(admin_pass)

        }

        save(d)

        print("Usuário inicial 'admin' criado com sucesso.")


def init_db():

    conn = get_conn()

    c = conn.cursor()

    try:

        estrutura_inicial = json.dumps({

            "alunos": {},

            "materias": {},

            "cursos": {},

            "professores": {},

            "turmas": {},

            "usuarios": {}

        })

        if DATABASE_URL:

            c.execute("""

                CREATE TABLE IF NOT EXISTS dados (

                    id INTEGER PRIMARY KEY DEFAULT 1,

                    conteudo JSONB NOT NULL

                )

            """)

            c.execute(

                f"INSERT INTO dados (id, conteudo) VALUES (1, %s) ON CONFLICT (id) DO NOTHING",

                [estrutura_inicial]

            )

        else:

            c.execute("""

                CREATE TABLE IF NOT EXISTS dados (

                    id INTEGER PRIMARY KEY DEFAULT 1,

                    conteudo TEXT NOT NULL

                )

            """)

            c.execute(

                "INSERT OR IGNORE INTO dados (id, conteudo) VALUES (1, ?)",

                [estrutura_inicial]

            )

        conn.commit()

    finally:

        c.close()

        conn.close()

    bootstrap_admin()


def load():

    conn = get_conn()

    c = conn.cursor()

    try:

        c.execute("SELECT conteudo FROM dados WHERE id = 1")

        row = c.fetchone()

        if not row:

            return {"alunos": {}, "materias": {}, "cursos": {}, "professores": {}, "turmas": {}, "usuarios": {}}

        val = row[0]

        d = json.loads(val) if isinstance(val, str) else val

        # Garante compatibilidade com dados antigos que não tinham as novas chaves

        for chave in ["usuarios", "cursos", "professores", "turmas"]:

            if chave not in d:

                d[chave] = {}

        return d

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


# ──────────────────────────────────────────────
# AUTH
# ──────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])

def login():

    erro = ""

    if request.method == "POST":

        ip = request.remote_addr or "unknown"

        allowed, reason = check_rate_limit(ip)

        if not allowed:

            return render_template("login.html", erro=reason)

        usuario = sanitize(request.form.get("usuario", ""))

        senha = request.form.get("senha", "")

        if not usuario or not senha:

            erro = "Usuário e senha são obrigatórios."

            register_login_failure(ip)

        else:

            d = load()

            user_data = d.get("usuarios", {}).get(usuario)

            if user_data and check_password_hash(user_data["senha_hash"], senha):

                session.clear()

                session["logado"] = True

                session["usuario"] = usuario

                session["nome"] = user_data.get("nome", usuario)

                reset_login_attempts(ip)

                return redirect(url_for("index"))

            else:

                erro = "Usuário ou senha incorretos."

                register_login_failure(ip)

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


# ──────────────────────────────────────────────
# API DADOS (leitura geral)
# ──────────────────────────────────────────────

@app.route("/api/dados")

@login_required

def get_dados():

    return jsonify(load())


# ──────────────────────────────────────────────
# CURSOS
# ──────────────────────────────────────────────

@app.route("/api/cursos", methods=["POST"])

@login_required

def add_curso():

    d = load()

    body = request.json

    nome = sanitize(body.get("nome", ""))

    descricao = sanitize(body.get("descricao", ""))

    if not nome:

        return jsonify({"erro": "Nome do curso é obrigatório."}), 400

    if any(c["nome"].lower() == nome.lower() for c in d["cursos"].values()):

        return jsonify({"erro": "Curso já cadastrado."}), 400

    curso_id = str(uuid.uuid4())[:8]

    while curso_id in d["cursos"]:

        curso_id = str(uuid.uuid4())[:8]

    d["cursos"][curso_id] = {"nome": nome, "descricao": descricao}

    save(d)

    return jsonify({"ok": True, "id": curso_id})


@app.route("/api/cursos/<curso_id>", methods=["PUT"])

@login_required

def edit_curso(curso_id):

    d = load()

    curso_id = sanitize(curso_id)

    if curso_id not in d["cursos"]:

        return jsonify({"erro": "Curso não encontrado."}), 404

    nome = sanitize(request.json.get("nome", ""))

    descricao = sanitize(request.json.get("descricao", ""))

    if not nome:

        return jsonify({"erro": "Nome é obrigatório."}), 400

    if any(c["nome"].lower() == nome.lower() and k != curso_id for k, c in d["cursos"].items()):

        return jsonify({"erro": "Já existe um curso com esse nome."}), 400

    d["cursos"][curso_id]["nome"] = nome

    d["cursos"][curso_id]["descricao"] = descricao

    save(d)

    return jsonify({"ok": True})


@app.route("/api/cursos/<curso_id>", methods=["DELETE"])

@login_required

def del_curso(curso_id):

    d = load()

    curso_id = sanitize(curso_id)

    if curso_id not in d["cursos"]:

        return jsonify({"erro": "Curso não encontrado."}), 404

    # Remove referência do curso nas matérias

    for mat in d["materias"].values():

        if mat.get("curso_id") == curso_id:

            mat["curso_id"] = None

    del d["cursos"][curso_id]

    save(d)

    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# PROFESSORES
# ──────────────────────────────────────────────

@app.route("/api/professores", methods=["POST"])

@login_required

def add_professor():

    d = load()

    body = request.json

    nome = sanitize(body.get("nome", ""))

    email = sanitize(body.get("email", ""))

    if not nome:

        return jsonify({"erro": "Nome do professor é obrigatório."}), 400

    if any(p["nome"].lower() == nome.lower() for p in d["professores"].values()):

        return jsonify({"erro": "Professor já cadastrado."}), 400

    prof_id = str(uuid.uuid4())[:8]

    while prof_id in d["professores"]:

        prof_id = str(uuid.uuid4())[:8]

    d["professores"][prof_id] = {"nome": nome, "email": email, "materias": []}

    save(d)

    return jsonify({"ok": True, "id": prof_id})


@app.route("/api/professores/<prof_id>", methods=["PUT"])

@login_required

def edit_professor(prof_id):

    d = load()

    prof_id = sanitize(prof_id)

    if prof_id not in d["professores"]:

        return jsonify({"erro": "Professor não encontrado."}), 404

    nome = sanitize(request.json.get("nome", ""))

    email = sanitize(request.json.get("email", ""))

    if not nome:

        return jsonify({"erro": "Nome é obrigatório."}), 400

    if any(p["nome"].lower() == nome.lower() and k != prof_id for k, p in d["professores"].items()):

        return jsonify({"erro": "Já existe um professor com esse nome."}), 400

    d["professores"][prof_id]["nome"] = nome

    d["professores"][prof_id]["email"] = email

    save(d)

    return jsonify({"ok": True})


@app.route("/api/professores/<prof_id>", methods=["DELETE"])

@login_required

def del_professor(prof_id):

    d = load()

    prof_id = sanitize(prof_id)

    if prof_id not in d["professores"]:

        return jsonify({"erro": "Professor não encontrado."}), 404

    # Remove professor das matérias que ele leciona

    for mat in d["materias"].values():

        if mat.get("professor_id") == prof_id:

            mat["professor_id"] = None

            mat["professor"] = ""

    del d["professores"][prof_id]

    save(d)

    return jsonify({"ok": True})


@app.route("/api/professores/<prof_id>/materias", methods=["POST"])

@login_required

def assoc_materia_professor(prof_id):

    """Atribui uma matéria a um professor."""

    d = load()

    prof_id = sanitize(prof_id)

    materia = sanitize(request.json.get("materia", ""))

    if prof_id not in d["professores"]:

        return jsonify({"erro": "Professor não encontrado."}), 404

    if materia not in d["materias"]:

        return jsonify({"erro": "Matéria não encontrada."}), 404

    prof = d["professores"][prof_id]

    if materia not in prof["materias"]:

        prof["materias"].append(materia)

    # Atualiza também a matéria com o professor responsável

    d["materias"][materia]["professor_id"] = prof_id

    d["materias"][materia]["professor"] = prof["nome"]

    save(d)

    return jsonify({"ok": True})


@app.route("/api/professores/<prof_id>/materias/<materia>", methods=["DELETE"])

@login_required

def desassoc_materia_professor(prof_id, materia):

    """Remove atribuição de matéria de um professor."""

    d = load()

    prof_id = sanitize(prof_id)

    materia = sanitize(materia)

    prof = d["professores"].get(prof_id)

    if prof and materia in prof["materias"]:

        prof["materias"].remove(materia)

        if d["materias"].get(materia, {}).get("professor_id") == prof_id:

            d["materias"][materia]["professor_id"] = None

            d["materias"][materia]["professor"] = ""

        save(d)

    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# MATÉRIAS (agora vinculadas a cursos)
# ──────────────────────────────────────────────

@app.route("/api/materias", methods=["POST"])

@login_required

def add_materia():

    d = load()

    body = request.json

    nome = sanitize(body.get("nome", ""))

    prof = sanitize(body.get("professor", ""))

    curso_id = sanitize(body.get("curso_id", ""))

    if not nome:

        return jsonify({"erro": "Nome da matéria é obrigatório."}), 400

    if nome in d["materias"]:

        return jsonify({"erro": "Matéria já existe."}), 400

    if curso_id and curso_id not in d["cursos"]:

        return jsonify({"erro": "Curso não encontrado."}), 404

    d["materias"][nome] = {

        "professor": prof,

        "professor_id": None,

        "curso_id": curso_id if curso_id else None,

        "chamadas": {},

        "notas": {}

    }

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

    # Remove das listas de professores

    for prof in d["professores"].values():

        if nome in prof.get("materias", []):

            prof["materias"].remove(nome)

    save(d)

    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# TURMAS
# ──────────────────────────────────────────────

@app.route("/api/turmas", methods=["POST"])

@login_required

def add_turma():

    d = load()

    body = request.json

    nome = sanitize(body.get("nome", ""))

    curso_id = sanitize(body.get("curso_id", ""))

    ano = sanitize(body.get("ano", ""))

    if not nome:

        return jsonify({"erro": "Nome da turma é obrigatório."}), 400

    if any(t["nome"].lower() == nome.lower() for t in d["turmas"].values()):

        return jsonify({"erro": "Turma já cadastrada."}), 400

    if curso_id and curso_id not in d["cursos"]:

        return jsonify({"erro": "Curso não encontrado."}), 404

    turma_id = str(uuid.uuid4())[:8]

    while turma_id in d["turmas"]:

        turma_id = str(uuid.uuid4())[:8]

    d["turmas"][turma_id] = {

        "nome": nome,

        "curso_id": curso_id if curso_id else None,

        "ano": ano,

        "alunos": []

    }

    save(d)

    return jsonify({"ok": True, "id": turma_id})


@app.route("/api/turmas/<turma_id>", methods=["PUT"])

@login_required

def edit_turma(turma_id):

    d = load()

    turma_id = sanitize(turma_id)

    if turma_id not in d["turmas"]:

        return jsonify({"erro": "Turma não encontrada."}), 404

    nome = sanitize(request.json.get("nome", ""))

    curso_id = sanitize(request.json.get("curso_id", ""))

    ano = sanitize(request.json.get("ano", ""))

    if not nome:

        return jsonify({"erro": "Nome é obrigatório."}), 400

    if any(t["nome"].lower() == nome.lower() and k != turma_id for k, t in d["turmas"].items()):

        return jsonify({"erro": "Já existe uma turma com esse nome."}), 400

    d["turmas"][turma_id]["nome"] = nome

    d["turmas"][turma_id]["curso_id"] = curso_id if curso_id else None

    d["turmas"][turma_id]["ano"] = ano

    save(d)

    return jsonify({"ok": True})


@app.route("/api/turmas/<turma_id>", methods=["DELETE"])

@login_required

def del_turma(turma_id):

    d = load()

    turma_id = sanitize(turma_id)

    if turma_id not in d["turmas"]:

        return jsonify({"erro": "Turma não encontrada."}), 404

    del d["turmas"][turma_id]

    save(d)

    return jsonify({"ok": True})


@app.route("/api/turmas/<turma_id>/alunos", methods=["POST"])

@login_required

def add_aluno_turma(turma_id):

    """Associa um aluno já cadastrado a uma turma."""

    d = load()

    turma_id = sanitize(turma_id)

    matricula = sanitize(request.json.get("matricula", ""))

    if turma_id not in d["turmas"]:

        return jsonify({"erro": "Turma não encontrada."}), 404

    if matricula not in d["alunos"]:

        return jsonify({"erro": "Aluno não encontrado."}), 404

    turma = d["turmas"][turma_id]

    if matricula not in turma["alunos"]:

        turma["alunos"].append(matricula)

    save(d)

    return jsonify({"ok": True})


@app.route("/api/turmas/<turma_id>/alunos/<matricula>", methods=["DELETE"])

@login_required

def remove_aluno_turma(turma_id, matricula):

    """Remove um aluno de uma turma."""

    d = load()

    turma_id = sanitize(turma_id)

    matricula = sanitize(matricula)

    turma = d["turmas"].get(turma_id)

    if turma and matricula in turma["alunos"]:

        turma["alunos"].remove(matricula)

        save(d)

    return jsonify({"ok": True})


@app.route("/api/turmas/<turma_id>/materias", methods=["POST"])

@login_required

def add_materia_turma_bulk(turma_id):

    """Associa as matérias do curso de uma turma a todos os alunos da turma."""

    d = load()

    turma_id = sanitize(turma_id)

    materia = sanitize(request.json.get("materia", ""))

    if turma_id not in d["turmas"]:

        return jsonify({"erro": "Turma não encontrada."}), 404

    if materia not in d["materias"]:

        return jsonify({"erro": "Matéria não encontrada."}), 404

    turma = d["turmas"][turma_id]

    for matricula in turma["alunos"]:

        aluno = d["alunos"].get(matricula)

        if aluno and materia not in aluno["materias"]:

            aluno["materias"].append(materia)

    save(d)

    return jsonify({"ok": True})


# ──────────────────────────────────────────────
# ALUNOS
# ──────────────────────────────────────────────

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

    # Remove das turmas

    for turma in d["turmas"].values():

        if matricula in turma.get("alunos", []):

            turma["alunos"].remove(matricula)

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


# ──────────────────────────────────────────────
# CHAMADA E NOTAS (inalterados)
# ──────────────────────────────────────────────

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
