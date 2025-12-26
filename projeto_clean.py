import json
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from flask import Flask, request, redirect, url_for, flash, render_template, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import calendar
from io import BytesIO
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'chave_financeira_v20_final_sync_fix_chart_v4_backup_completo' 
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=365)

# ============================================
# CONFIGURAÇÃO DO BANCO DE DADOS (PostgreSQL Neon)
# ============================================
import os
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://neondb_owner:npg_NA4wBru6LHOZ@ep-jolly-lab-ahhyx7m1-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require')
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 300,
    'pool_pre_ping': True,
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'warning'

# ============================================
# MODELOS DO BANCO DE DADOS
# ============================================

class User(UserMixin, db.Model):
    """Modelo de Usuário para autenticação"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_month_viewed = db.Column(db.String(7), nullable=True)  # Formato: YYYY-MM
    
    # Relacionamentos
    transactions = db.relationship('Transaction', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    fixed_expenses = db.relationship('FixedExpense', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    goals = db.relationship('Goal', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    generation_logs = db.relationship('GenerationLog', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class Transaction(db.Model):
    """Modelo de Transações (substitui o Excel)"""
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data = db.Column(db.Date, nullable=False)
    ano_mes = db.Column(db.String(7), nullable=False)  # Formato: YYYY-MM
    categoria = db.Column(db.String(100), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # ENTRADA ou SAIDA
    descricao = db.Column(db.String(255), nullable=True)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='Pendente')  # Pendente ou Pago
    classificacao = db.Column(db.String(50), default='Essenciais')  # Essenciais, Estilo de Vida, Investimentos
    fixado = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Transaction {self.id}: {self.descricao} - R${self.valor}>'


class FixedExpense(db.Model):
    """Modelo de Despesas Fixas (substitui lancamentos_fixos.json)"""
    __tablename__ = 'fixed_expenses'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # ENTRADA ou SAIDA
    categoria = db.Column(db.String(100), nullable=False)
    descricao = db.Column(db.String(255), nullable=True)
    valor = db.Column(db.Float, nullable=False)
    dia_fixo = db.Column(db.Integer, nullable=False)  # Dia do mês (1-31)
    classificacao = db.Column(db.String(50), default='Essenciais')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<FixedExpense {self.descricao}: R${self.valor} dia {self.dia_fixo}>'


class Goal(db.Model):
    """Modelo de Metas (substitui metas.json)"""
    __tablename__ = 'goals'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    descricao = db.Column(db.String(255), nullable=False)
    valor_alvo = db.Column(db.Float, nullable=False)
    valor_atual = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def percentual(self):
        if self.valor_alvo <= 0:
            return 0
        return round((self.valor_atual / self.valor_alvo) * 100, 1)
    
    def __repr__(self):
        return f'<Goal {self.descricao}: {self.percentual}%>'


class GenerationLog(db.Model):
    """Modelo de Log de Geração de Fixos (substitui log_geracao_fixos.json)"""
    __tablename__ = 'generation_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ano_mes = db.Column(db.String(7), nullable=False)  # Formato: YYYY-MM
    generated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'ano_mes', name='unique_user_month'),
    )
    
    def __repr__(self):
        return f'<GenerationLog {self.user_id} - {self.ano_mes}>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ============================================
# CATEGORIAS PADRÃO
# ============================================
DEFAULT_CATEGORIES = [
    'Alimentação', 'Moradia', 'Transporte', 'Saúde', 'Educação',
    'Lazer', 'Contas Fixas', 'Investimentos', 'Salário', 'Outras Entradas', 'Outros Gastos'
]


# ============================================
# FUNÇÕES DE ACESSO AO BANCO DE DADOS
# ============================================

def get_user_transactions_df(user_id, ano_mes=None):
    """Carrega transações do usuário como DataFrame usando pd.read_sql"""
    query = Transaction.query.filter_by(user_id=user_id)
    if ano_mes:
        query = query.filter_by(ano_mes=ano_mes)
    
    df = pd.read_sql(query.statement, db.engine)
    
    if df.empty:
        # Retorna DataFrame vazio com colunas já renomeadas
        return pd.DataFrame(columns=['ID', 'user_id', 'Data', 'AnoMes', 'Categoria', 'Tipo', 
                                      'Descrição', 'Valor', 'Status', 'Classificação', 'Fixado'])
    
    # Converte coluna 'data' para datetime
    df['data'] = pd.to_datetime(df['data'])
    
    # Garante que ano_mes existe (caso venha vazio do banco)
    if 'ano_mes' not in df.columns or df['ano_mes'].isna().any():
        df['ano_mes'] = df['data'].dt.strftime('%Y-%m')
    
    # Renomeia colunas para manter compatibilidade com código legado
    df = df.rename(columns={
        'id': 'ID',
        'data': 'Data',
        'ano_mes': 'AnoMes',
        'categoria': 'Categoria',
        'tipo': 'Tipo',
        'descricao': 'Descrição',
        'valor': 'Valor',
        'status': 'Status',
        'classificacao': 'Classificação',
        'fixado': 'Fixado'
    })
    
    # Converte fixado de boolean para 'Sim'/'Não' para compatibilidade
    df['Fixado'] = df['Fixado'].apply(lambda x: 'Sim' if x else 'Não')
    
    return df


def get_all_categories(user_id=None):
    """Retorna todas as categorias (padrão + customizadas pelo usuário)"""
    final = list(DEFAULT_CATEGORIES)
    seen = set([c.lower() for c in final])
    
    if user_id:
        # Busca categorias únicas das transações do usuário
        user_cats = db.session.query(Transaction.categoria).filter_by(user_id=user_id).distinct().all()
        for (cat,) in user_cats:
            if cat and cat.lower() not in seen:
                seen.add(cat.lower())
                final.append(cat)
    
    return sorted(final)


def check_generation_log(user_id, ano_mes):
    """Verifica se os fixos já foram gerados para o mês"""
    log = GenerationLog.query.filter_by(user_id=user_id, ano_mes=ano_mes).first()
    return log is not None


def mark_generation_log(user_id, ano_mes):
    """Marca que os fixos foram gerados para o mês"""
    if not check_generation_log(user_id, ano_mes):
        log = GenerationLog(user_id=user_id, ano_mes=ano_mes)
        db.session.add(log)
        db.session.commit()


# ============================================
# FIXOS E SINCRONIZAÇÃO (REFATORADO PARA SQL)
# ============================================

def generate_monthly_entries(filtro_mes, user_id, force=False):
    """Gera lançamentos fixos para o mês (versão SQL)"""
    
    # Busca despesas fixas do usuário
    fixed_expenses = FixedExpense.query.filter_by(user_id=user_id).all()
    
    # Se não houver fixos, marca log e sai
    if not fixed_expenses:
        mark_generation_log(user_id, filtro_mes)
        return
    
    # Verifica se já foi gerado (a menos que force=True)
    if not force and check_generation_log(user_id, filtro_mes):
        return
    
    # 1. SINCRONIZAÇÃO - Atualiza transações existentes que batem com fixos
    month_transactions = Transaction.query.filter_by(user_id=user_id, ano_mes=filtro_mes).all()
    
    for trans in month_transactions:
        desc_atual = (trans.descricao or '').strip().lower()
        for fixed in fixed_expenses:
            desc_rule = (fixed.descricao or '').strip().lower()
            is_match = False
            if desc_atual == desc_rule:
                is_match = True
            elif len(desc_atual) > 3 and desc_atual in desc_rule:
                is_match = True
            elif len(desc_rule) > 3 and desc_rule in desc_atual:
                is_match = True
            
            if is_match:
                if not trans.fixado or trans.classificacao != fixed.classificacao:
                    trans.fixado = True
                    trans.classificacao = fixed.classificacao
                    trans.categoria = fixed.categoria
                break
    
    db.session.commit()
    
    # 2. CRIAÇÃO DE NOVOS LANÇAMENTOS
    try:
        dt_month = datetime.strptime(filtro_mes, '%Y-%m')
    except:
        return
    
    new_count = 0
    for fixed in fixed_expenses:
        nome_fixo = (fixed.descricao or '').strip().lower()
        
        # Verifica se já existe lançamento similar no mês
        exists = False
        for trans in month_transactions:
            nome_existente = (trans.descricao or '').strip().lower()
            if nome_fixo == nome_existente or \
               (len(nome_fixo) > 3 and nome_fixo in nome_existente) or \
               (len(nome_existente) > 3 and nome_existente in nome_fixo):
                exists = True
                break
        
        if exists:
            continue
        
        # Calcula a data do lançamento
        try:
            day = min(int(fixed.dia_fixo), calendar.monthrange(dt_month.year, dt_month.month)[1])
            data_lanc = datetime(dt_month.year, dt_month.month, day).date()
        except:
            continue
        
        # Calcula valor (negativo para saída)
        val = float(fixed.valor)
        if fixed.tipo == 'SAIDA':
            val = abs(val) * -1
        else:
            val = abs(val)
        
        # Cria nova transação
        new_trans = Transaction(
            user_id=user_id,
            data=data_lanc,
            ano_mes=filtro_mes,
            categoria=fixed.categoria,
            tipo=fixed.tipo,
            descricao=fixed.descricao,
            valor=val,
            status='Pendente',
            classificacao=fixed.classificacao,
            fixado=True
        )
        db.session.add(new_trans)
        new_count += 1
    
    if new_count > 0:
        db.session.commit()
        flash(f"{new_count} lançamentos fixos gerados.", 'success')
    
    # Marca no log que foi gerado
    mark_generation_log(user_id, filtro_mes)

# --- CALCULOS ---
def calculate_trend_indicators(df_user, current_month_str):
    """Calcula indicadores de tendência (comparação com mês anterior)"""
    try:
        curr = df_user[df_user['AnoMes'] == current_month_str]
        prev_dt = datetime.strptime(current_month_str, '%Y-%m') - relativedelta(months=1)
        prev = df_user[df_user['AnoMes'] == prev_dt.strftime('%Y-%m')]
        c_e = curr[curr['Valor'] > 0]['Valor'].sum()
        c_s = abs(curr[curr['Valor'] < 0]['Valor'].sum())
        p_e = prev[prev['Valor'] > 0]['Valor'].sum()
        p_s = abs(prev[prev['Valor'] < 0]['Valor'].sum())
        def pct(c, p): return ((c - p) / p) * 100 if p != 0 else (100 if c > 0 else 0)
        return pct(c_e, p_e), pct(c_s, p_s)
    except: 
        return 0, 0

def calculate_historical_average(df_user):
    """Calcula média histórica de entradas e saídas"""
    if df_user.empty: 
        return 0.0, 0.0
    grp = df_user.groupby('AnoMes')['Valor'].agg([lambda x: x[x>0].sum(), lambda x: abs(x[x<0].sum())])
    return (grp.iloc[:, 0].mean() if not grp.empty else 0, grp.iloc[:, 1].mean() if not grp.empty else 0)

def get_monthly_finance_data(filtro_mes, user_id, run_fixed=False):
    """Obtém dados financeiros do mês usando SQL"""
    if run_fixed: 
        generate_monthly_entries(filtro_mes, user_id)
    
    # Carrega todas as transações do usuário via SQL
    df_user = get_user_transactions_df(user_id)
    
    # Calcula indicadores de tendência e média
    trend_ent, trend_sai = calculate_trend_indicators(df_user, filtro_mes)
    avg_ent, avg_sai = calculate_historical_average(df_user)
    
    # Filtra apenas o mês atual
    df_filtrado = df_user[df_user['AnoMes'] == filtro_mes].copy()
    
    if not df_filtrado.empty:
        # Ordenação: Tipo (Entrada/Saida) -> Data -> ID
        df_filtrado['_Sort_Data'] = pd.to_datetime(df_filtrado['Data'], errors='coerce')
        df_filtrado['_Sort_Tipo'] = df_filtrado['Tipo'].apply(
            lambda x: 0 if str(x).strip().upper() in ['ENTRADA', 'RECEITA'] else 1
        )
        df_filtrado = df_filtrado.sort_values(
            by=['_Sort_Tipo', '_Sort_Data', 'ID'], 
            ascending=[True, True, True]
        )
        df_filtrado.drop(columns=['_Sort_Data', '_Sort_Tipo'], inplace=True)

    # Cálculos financeiros
    entrada = df_filtrado[df_filtrado['Valor'] > 0]['Valor'].sum()
    saida = df_filtrado[df_filtrado['Valor'] < 0]['Valor'].sum()
    saldo = df_filtrado['Valor'].sum()
    gastos_cat = df_filtrado[df_filtrado['Tipo'] == 'SAIDA'].groupby('Categoria')['Valor'].sum().abs()
    
    # Dados para gráfico diário
    chart_days, chart_in, chart_out, chart_bal = [], [], [], []
    if not df_filtrado.empty:
        df_chart = df_filtrado.copy()
        df_chart['_Sort_Data'] = pd.to_datetime(df_chart['Data'], errors='coerce')
        df_chart = df_chart.sort_values(by=['_Sort_Data'])
        
        grp_day = df_chart.groupby(df_chart['_Sort_Data'].dt.day)
        for day in sorted(grp_day.groups.keys()):
            g = grp_day.get_group(day)
            e = g[g['Valor'] > 0]['Valor'].sum()
            s = abs(g[g['Valor'] < 0]['Valor'].sum())
            chart_days.append(str(int(day)))
            chart_in.append(e)
            chart_out.append(s)
            chart_bal.append(e - s)

    # Macro categorias (50-30-20)
    macro = {'ESSENCIAIS': 0.0, 'ESTILO_VIDA': 0.0, 'INVESTIMENTOS': 0.0}
    macro_lists = {'ESSENCIAIS': set(), 'ESTILO_VIDA': set(), 'INVESTIMENTOS': set()}
    for _, row in df_filtrado[df_filtrado['Valor'] < 0].iterrows():
        c = str(row.get('Classificação', 'Essenciais')).upper()
        v = abs(row['Valor'])
        desc = str(row['Descrição']).strip()
        item_name = desc if desc and desc.lower() != 'nan' else str(row['Categoria']).strip()
        key = 'ESSENCIAIS'
        if 'ESTILO' in c: key = 'ESTILO_VIDA'
        elif 'INVEST' in c: key = 'INVESTIMENTOS'
        macro[key] += v
        macro_lists[key].add(item_name)
    macro_tooltips = {k: ', '.join(sorted(list(v))) if v else "Nenhum item" for k, v in macro_lists.items()}

    # Formata dados para exibição
    dados_exibicao = []
    for _, row in df_filtrado.iterrows():
        dados_exibicao.append({
            'ID': row['ID'],
            'Data': row['Data'].strftime('%d/%m/%Y') if hasattr(row['Data'], 'strftime') else str(row['Data']),
            'Tipo': row['Tipo'],
            'Categoria': row['Categoria'],
            'Descrição': row['Descrição'],
            'Valor': row['Valor'],
            'Status': row['Status'],
            'Classificação': row['Classificação'],
            'Fixado': row['Fixado']
        })

    return float(entrada), float(saida), float(saldo), dados_exibicao, \
           gastos_cat.index.tolist(), gastos_cat.values.tolist(), \
           chart_days, chart_in, chart_out, chart_bal, df_user, \
           trend_ent, trend_sai, macro, avg_ent, avg_sai, macro_tooltips

def get_yearly_finance_data(ano, user_id):
    """Obtém dados financeiros do ano usando SQL"""
    # Carrega transações do usuário
    df = get_user_transactions_df(user_id)
    
    # Filtra pelo ano
    df = df[df['AnoMes'].str.startswith(str(ano), na=False)]
    
    # Agrupa por mês
    if not df.empty:
        grp = df.groupby('AnoMes')['Valor'].agg(['sum', lambda x: x[x>0].sum(), lambda x: x[x<0].sum()])
    else:
        grp = pd.DataFrame()
    meses = ['JAN','FEV','MAR','ABR','MAI','JUN','JUL','AGO','SET','OUT','NOV','DEZ']
    res, lbs, e, s, sl = [], [], [], [], []
    for i in range(1, 13):
        k = f'{ano}-{i:02d}'
        row = grp.loc[k] if k in grp.index else [0,0,0]
        ent_val = float(row[1] if k in grp.index else 0)
        sai_val = abs(float(row[2] if k in grp.index else 0))
        sal_val = float(row[0] if k in grp.index else 0)
        res.append({'Periodo': meses[i-1], 'Entrada': ent_val, 'Saida': sai_val, 'Saldo': sal_val})
        lbs.append(meses[i-1]); e.append(ent_val); s.append(sai_val); sl.append(sal_val)
    return res, sum(e), sum(s), sum(sl), lbs, e, s, sl, df

# --- IMPORT ---
def processar_importacao(file_obj, user_id):
    """Importa transações de planilha Excel para o banco de dados"""
    try:
        df_dict = pd.read_excel(file_obj, sheet_name=None)
        nome_aba = next((k for k in df_dict if "LAN" in k.upper() or "DAD" in k.upper()), list(df_dict.keys())[0])
        df_temp = pd.read_excel(file_obj, sheet_name=nome_aba, header=None)
        idx = next((i for i, r in df_temp.iterrows() if any('DATA' in str(s).upper() for s in r) and any('VALOR' in str(s).upper() for s in r)), 0)
        file_obj.seek(0)
        df = pd.read_excel(file_obj, sheet_name=nome_aba, header=idx)
        df.columns = [str(c).upper().strip() for c in df.columns]
        
        col_d = next((c for c in df.columns if 'DATA' in c), None)
        col_v = next((c for c in df.columns if 'VALOR' in c), None)
        col_desc = next((c for c in df.columns if 'DESC' in c or 'HIS' in c), None)
        col_tipo = next((c for c in df.columns if 'TIP' in c or 'E/S' in c), None)
        
        if not col_d or not col_v: 
            return 0
        
        # Busca transações existentes para evitar duplicatas
        existing_transactions = Transaction.query.filter_by(user_id=user_id).all()
        existing_set = set()
        for t in existing_transactions:
            key = (t.data, t.descricao, t.valor)
            existing_set.add(key)
        
        novos_count = 0
        for _, r in df.iterrows():
            if pd.isna(r[col_d]) or pd.isna(r[col_v]): 
                continue
            try: 
                d_val = r[col_d]
                if isinstance(d_val, datetime):
                    data_obj = d_val.date()
                else:
                    data_obj = pd.to_datetime(d_val, dayfirst=True).date()
                am = data_obj.strftime('%Y-%m')
            except: 
                continue
            
            val = float(r[col_v])
            tipo = 'ENTRADA'
            if col_tipo:
                if 'S' in str(r[col_tipo]).upper(): 
                    tipo = 'SAIDA'
                    val = abs(val) * -1
                else: 
                    val = abs(val)
            else:
                if val < 0: 
                    tipo = 'SAIDA'
                else: 
                    tipo = 'ENTRADA'
            
            desc = str(r.get(col_desc, 'Importado')).strip() if col_desc else 'Importado'
            
            # Verifica se já existe
            if (data_obj, desc, val) in existing_set:
                continue
            
            # Cria nova transação
            new_trans = Transaction(
                user_id=user_id,
                data=data_obj,
                ano_mes=am,
                categoria='Importado',
                tipo=tipo,
                descricao=desc,
                valor=val,
                status='Pendente',
                classificacao='Essenciais',
                fixado=False
            )
            db.session.add(new_trans)
            novos_count += 1
        
        if novos_count > 0:
            db.session.commit()
        
        return novos_count
    except Exception as e:
        db.session.rollback()
        print(f"Erro na importação: {e}")
        return -1

# --- TEMPLATES MOVIDOS PARA templates/index.html e templates/login.html ---
# Os templates HTML agora estão em arquivos separados na pasta templates/

# --- ROTAS ---
@app.route('/')
@app.route('/dashboard')
@login_required
def dashboard():
    user_id = current_user.id
    hoje = datetime.now()
    session.permanent = True 
    
    # Gerencia filtro de mês
    arg_mes = request.args.get('filtro_mes')
    if arg_mes:
        filtro = arg_mes
        current_user.last_month_viewed = filtro
        db.session.commit()
        session['last_month'] = filtro
    else:
        saved_db = current_user.last_month_viewed
        saved_sess = session.get('last_month')
        if saved_db: 
            filtro = saved_db
        elif saved_sess: 
            filtro = saved_sess
        else: 
            filtro = hoje.strftime('%Y-%m')

    # Verifica se precisa gerar fixos
    ask_to_generate = not check_generation_log(user_id, filtro)
    
    # Obtém dados financeiros
    (ent, sai, sal, dados, cats, vals, days, d_in, d_out, d_bal, df_u, t_ent, t_sai, macro, avg_ent, avg_sai, tooltips) = get_monthly_finance_data(filtro, user_id, run_fixed=False)
    
    meses = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'}
    try: 
        dt = datetime.strptime(filtro, '%Y-%m')
        mes_ext = meses[dt.month]
        ano_ext = dt.year
    except: 
        mes_ext = 'Atual'
        ano_ext = hoje.year
    
    return render_template('index.html',
        active_page='dashboard',
        user=current_user.username,
        entrada=ent,
        saida=sai,
        saldo=sal,
        dados_exibicao=dados,
        chart_cats=json.dumps(cats),
        chart_vals=json.dumps(vals),
        chart_days=json.dumps(days),
        chart_daily_in=json.dumps(d_in),
        chart_daily_out=json.dumps(d_out),
        chart_daily_bal=json.dumps(d_bal),
        filtro_atual=filtro,
        mes_extenso=mes_ext,
        ano_extenso=ano_ext,
        hoje_br=hoje.strftime('%d/%m/%Y'),
        all_categories=get_all_categories(user_id),
        trend_ent_pct=t_ent,
        trend_sai_pct=t_sai,
        macro_vals=macro,
        avg_ent=avg_ent,
        avg_sai=avg_sai,
        macro_tooltips=tooltips,
        ask_to_generate=ask_to_generate
    )

@app.route('/gerar_fixos_cmd')
@login_required
def gerar_fixos_cmd():
    mes = request.args.get('mes')
    if mes: 
        generate_monthly_entries(mes, current_user.id, force=True)
    return redirect(url_for('dashboard', filtro_mes=mes))

@app.route('/toggle_status/<int:id>')
@login_required
def toggle_status(id):
    """Alterna o status de uma transação entre Pendente e Pago"""
    trans = Transaction.query.filter_by(id=id, user_id=current_user.id).first()
    filtro_retorno = request.args.get('filtro_mes')
    
    if trans:
        trans.status = 'Pago' if trans.status != 'Pago' else 'Pendente'
        db.session.commit()
        if not filtro_retorno:
            filtro_retorno = trans.ano_mes
    
    if not filtro_retorno: 
        filtro_retorno = datetime.now().strftime('%Y-%m')
    return redirect(url_for('dashboard', filtro_mes=filtro_retorno))

@app.route('/add_lancamento', methods=['POST'])
@login_required
def add_lancamento():
    """Adiciona uma nova transação"""
    try:
        d = datetime.strptime(request.form['data'], '%d/%m/%Y')
        v = float(request.form['valor']) * (-1 if request.form['tipo'] == 'SAIDA' else 1)
        
        new_trans = Transaction(
            user_id=current_user.id,
            data=d.date(),
            ano_mes=d.strftime('%Y-%m'),
            categoria=request.form['categoria'],
            tipo=request.form['tipo'],
            descricao=request.form['descricao'],
            valor=v,
            classificacao=request.form['classificacao'],
            status='Pendente',
            fixado=False
        )
        db.session.add(new_trans)
        db.session.commit()
        return redirect(url_for('dashboard', filtro_mes=d.strftime('%Y-%m')))
    except Exception as e:
        db.session.rollback()
        flash(f'Erro ao adicionar: {e}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/edit_lancamento_form/<int:lancamento_id>')
@login_required
def edit_lancamento_form(lancamento_id):
    """Formulário de edição de transação"""
    trans = Transaction.query.filter_by(id=lancamento_id, user_id=current_user.id).first()
    if not trans: 
        return redirect(url_for('dashboard'))
    
    lancamento = {
        'ID': trans.id,
        'Data': trans.data.strftime('%d/%m/%Y'),
        'Tipo': trans.tipo,
        'Categoria': trans.categoria,
        'Descrição': trans.descricao,
        'Valor': trans.valor,
        'Classificação': trans.classificacao
    }
    return render_template('edit_lancamento.html',
        active_page='dashboard',
        user=current_user.username,
        lancamento=lancamento,
        categorias_orcamento=get_all_categories(current_user.id)
    )

@app.route('/edit_lancamento_save', methods=['POST'])
@login_required
def edit_lancamento_save():
    """Salva edição de transação"""
    trans = Transaction.query.filter_by(id=int(request.form['lancamento_id']), user_id=current_user.id).first()
    
    if trans:
        try:
            d = datetime.strptime(request.form['data'], '%d/%m/%Y')
            v = float(request.form['valor']) * (-1 if request.form['tipo'] == 'SAIDA' else 1)
            
            trans.data = d.date()
            trans.ano_mes = d.strftime('%Y-%m')
            trans.tipo = request.form['tipo']
            trans.categoria = request.form['categoria']
            trans.descricao = request.form['descricao']
            trans.valor = v
            trans.classificacao = request.form['classificacao']
            
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao editar: {e}', 'danger')
    
    filtro_retorno = request.form.get('filtro_mes_origem')
    if not filtro_retorno: 
        filtro_retorno = datetime.now().strftime('%Y-%m')
    return redirect(url_for('dashboard', filtro_mes=filtro_retorno))

@app.route('/delete_lancamento/<int:lancamento_id>')
@login_required
def delete_lancamento(lancamento_id):
    """Remove uma transação"""
    trans = Transaction.query.filter_by(id=lancamento_id, user_id=current_user.id).first()
    filtro_retorno = request.args.get('filtro_mes')
    
    if trans:
        if not filtro_retorno:
            filtro_retorno = trans.ano_mes
        db.session.delete(trans)
        db.session.commit()
    
    if not filtro_retorno: 
        filtro_retorno = datetime.now().strftime('%Y-%m')
    return redirect(url_for('dashboard', filtro_mes=filtro_retorno))

@app.route('/pin_lancamento/<int:lancamento_id>')
@login_required
def pin_lancamento(lancamento_id):
    """Fixa/desfixa uma transação como recorrente"""
    trans = Transaction.query.filter_by(id=lancamento_id, user_id=current_user.id).first()
    filtro_retorno = request.args.get('filtro_mes')
    
    if trans:
        # Alterna o status de fixado
        new_fixed_status = not trans.fixado
        trans.fixado = new_fixed_status
        
        if not filtro_retorno:
            filtro_retorno = trans.ano_mes
        
        # Remove fixo existente com mesma descrição
        desc_clean = (trans.descricao or '').strip().lower()
        existing_fixed = FixedExpense.query.filter_by(user_id=current_user.id).all()
        for fixed in existing_fixed:
            if (fixed.descricao or '').strip().lower() == desc_clean:
                db.session.delete(fixed)
        
        # Se está fixando, cria novo registro de despesa fixa
        if new_fixed_status:
            new_fixed = FixedExpense(
                user_id=current_user.id,
                tipo=trans.tipo,
                categoria=trans.categoria,
                descricao=trans.descricao,
                valor=abs(trans.valor),
                dia_fixo=trans.data.day,
                classificacao=trans.classificacao
            )
            db.session.add(new_fixed)
            flash('Lançamento fixado com sucesso!', 'success')
        
        db.session.commit()
    
    if not filtro_retorno: 
        filtro_retorno = datetime.now().strftime('%Y-%m')
    return redirect(url_for('dashboard', filtro_mes=filtro_retorno))

@app.route('/lancamentos_fixos')
@login_required
def lancamentos_fixos():
    """Lista despesas fixas do usuário"""
    fixed_list = FixedExpense.query.filter_by(user_id=current_user.id).order_by(FixedExpense.tipo, FixedExpense.dia_fixo).all()
    
    # Converte para formato compatível com template
    fixed_entries = []
    for f in fixed_list:
        fixed_entries.append((f.id, {
            'tipo': f.tipo,
            'categoria': f.categoria,
            'descricao': f.descricao,
            'valor': f.valor,
            'dia_fixo': f.dia_fixo,
            'classificacao': f.classificacao
        }))
    
    return render_template('fixos.html',
        active_page='fixos',
        user=current_user.username,
        fixed_entries=fixed_entries,
        categorias_orcamento=get_all_categories(current_user.id)
    )

@app.route('/add_fixo', methods=['POST'])
@login_required
def add_fixo():
    """Adiciona nova despesa fixa"""
    new_fixed = FixedExpense(
        user_id=current_user.id,
        tipo=request.form['tipo'],
        categoria=request.form['categoria'],
        descricao=request.form['descricao'],
        valor=float(request.form['valor']),
        dia_fixo=int(request.form['dia_fixo']),
        classificacao=request.form['classificacao']
    )
    db.session.add(new_fixed)
    db.session.commit()
    return redirect(url_for('lancamentos_fixos'))

@app.route('/delete_fixo/<int:id>')
@login_required
def delete_fixo(id):
    """Remove despesa fixa"""
    fixed = FixedExpense.query.filter_by(id=id, user_id=current_user.id).first()
    if fixed:
        db.session.delete(fixed)
        db.session.commit()
    return redirect(url_for('lancamentos_fixos'))

@app.route('/edit_fixo_form/<int:id>')
@login_required
def edit_fixo_form(id):
    """Formulário de edição de despesa fixa"""
    fixed = FixedExpense.query.filter_by(id=id, user_id=current_user.id).first()
    if not fixed: 
        return redirect(url_for('lancamentos_fixos'))
    
    lancamento_fixo = {
        'tipo': fixed.tipo,
        'categoria': fixed.categoria,
        'descricao': fixed.descricao,
        'valor': fixed.valor,
        'dia_fixo': fixed.dia_fixo,
        'classificacao': fixed.classificacao
    }
    return render_template('edit_fixo.html',
        active_page='fixos',
        user=current_user.username,
        fixo_id=id,
        lancamento_fixo=lancamento_fixo,
        categorias_orcamento=get_all_categories(current_user.id)
    )

@app.route('/edit_fixo_save/<int:id>', methods=['POST'])
@login_required
def edit_fixo_save(id):
    """Salva edição de despesa fixa"""
    fixed = FixedExpense.query.filter_by(id=id, user_id=current_user.id).first()
    if fixed:
        fixed.tipo = request.form['tipo']
        fixed.categoria = request.form['categoria']
        fixed.descricao = request.form['descricao']
        fixed.valor = float(request.form['valor'])
        fixed.dia_fixo = int(request.form['dia_fixo'])
        fixed.classificacao = request.form['classificacao']
        db.session.commit()
    return redirect(url_for('lancamentos_fixos'))

@app.route('/metas')
@login_required
def metas():
    """Lista metas do usuário"""
    user_goals = Goal.query.filter_by(user_id=current_user.id).all()
    
    # Converte para formato compatível com template
    metas_list = []
    for g in user_goals:
        metas_list.append((g.id, {
            'descricao': g.descricao,
            'valor_alvo': g.valor_alvo,
            'valor_atual': g.valor_atual
        }))
    
    return render_template('metas.html',
        active_page='metas',
        user=current_user.username,
        metas=metas_list
    )

@app.route('/add_meta', methods=['POST'])
@login_required
def add_meta():
    """Adiciona nova meta"""
    new_goal = Goal(
        user_id=current_user.id,
        descricao=request.form['descricao'],
        valor_alvo=float(request.form['valor_alvo']),
        valor_atual=float(request.form.get('valor_atual', 0))
    )
    db.session.add(new_goal)
    db.session.commit()
    flash('Meta criada com sucesso!', 'success')
    return redirect(url_for('metas'))

@app.route('/delete_meta/<int:id>')
@login_required
def delete_meta(id):
    """Remove meta"""
    goal = Goal.query.filter_by(id=id, user_id=current_user.id).first()
    if goal:
        db.session.delete(goal)
        db.session.commit()
    return redirect(url_for('metas'))

@app.route('/add_valor_meta', methods=['POST'])
@login_required
def add_valor_meta():
    """Adiciona valor a uma meta"""
    goal = Goal.query.filter_by(id=int(request.form['meta_id']), user_id=current_user.id).first()
    if goal:
        valor = float(request.form['valor'])
        goal.valor_atual += valor
        db.session.commit()
        flash(f'Adicionado R$ {valor:.2f} à meta!', 'success')
    return redirect(url_for('metas'))

@app.route('/relatorio_anual')
@login_required
def relatorio_anual():
    """Relatório anual"""
    ano = int(request.args.get('filtro_ano', datetime.now().year))
    res, te, ts, tsal, lbs, e, s, sl, _ = get_yearly_finance_data(ano, current_user.id)
    return render_template('relatorio.html',
        active_page='relatorio',
        user=current_user.username,
        ano_atual=ano,
        relatorio_anual_data=res,
        total_entrada=te,
        total_saida=ts,
        total_saldo=tsal,
        chart_labels=json.dumps(lbs),
        chart_entrada=json.dumps(e),
        chart_saida=json.dumps(s),
        chart_saldo=json.dumps(sl)
    )

# --- BACKUP E RESTAURAÇÃO ---
@app.route('/backup_json')
@login_required
def backup_json():
    """Gera backup completo em JSON"""
    # Transações
    transactions = Transaction.query.filter_by(user_id=current_user.id).all()
    trans_list = []
    for t in transactions:
        trans_list.append({
            'data': t.data.strftime('%Y-%m-%d'),
            'ano_mes': t.ano_mes,
            'categoria': t.categoria,
            'tipo': t.tipo,
            'descricao': t.descricao,
            'valor': t.valor,
            'status': t.status,
            'classificacao': t.classificacao,
            'fixado': t.fixado
        })
    
    # Despesas Fixas
    fixed_expenses = FixedExpense.query.filter_by(user_id=current_user.id).all()
    fixed_list = []
    for f in fixed_expenses:
        fixed_list.append({
            'tipo': f.tipo,
            'categoria': f.categoria,
            'descricao': f.descricao,
            'valor': f.valor,
            'dia_fixo': f.dia_fixo,
            'classificacao': f.classificacao
        })
    
    # Metas
    goals = Goal.query.filter_by(user_id=current_user.id).all()
    goals_list = []
    for g in goals:
        goals_list.append({
            'descricao': g.descricao,
            'valor_alvo': g.valor_alvo,
            'valor_atual': g.valor_atual
        })
    
    backup_data = {
        "transactions": trans_list,
        "fixed_expenses": fixed_list,
        "goals": goals_list
    }
    
    b = BytesIO()
    b.write(json.dumps(backup_data, indent=4, ensure_ascii=False).encode('utf-8'))
    b.seek(0)
    
    return send_file(b, as_attachment=True, download_name=f'backup_{current_user.username}_{datetime.now().strftime("%Y%m%d")}.json', mimetype='application/json')

@app.route('/restore_backup', methods=['POST'])
@login_required
def restore_backup():
    """Restaura backup de JSON para o banco de dados SQL"""
    
    def get_value(item, *keys):
        """Helper para buscar valor com múltiplas variações de chaves"""
        for key in keys:
            if key in item:
                return item[key]
        return None
    
    if request.files.get('backup_file'):
        try:
            file_content = json.load(request.files['backup_file'])
            
            if isinstance(file_content, dict):
                contador_trans = 0
                contador_fixos = 0
                contador_metas = 0
                duplicatas = 0
                
                # ========== RESTAURA TRANSAÇÕES ==========
                if "transactions" in file_content:
                    for t in file_content["transactions"]:
                        try:
                            # Busca data com múltiplas variações
                            data_str = get_value(t, 'Data', 'data', 'DATE')
                            
                            if not data_str:
                                print("⚠️ Transação sem data, pulando...")
                                continue
                            
                            # Conversão flexível de data (múltiplos formatos)
                            if isinstance(data_str, str):
                                if 'T' in data_str:  # ISO format (2024-12-23T00:00:00)
                                    data_obj = datetime.fromisoformat(data_str.replace('Z', '+00:00')).date()
                                elif '-' in data_str and len(data_str) == 10:  # YYYY-MM-DD
                                    data_obj = datetime.strptime(data_str, '%Y-%m-%d').date()
                                else:  # DD/MM/YYYY
                                    data_obj = datetime.strptime(data_str, '%d/%m/%Y').date()
                            else:
                                data_obj = data_str
                            
                            # Busca outros campos com variações
                            ano_mes = get_value(t, 'AnoMes', 'ano_mes', 'Ano_Mes') or data_obj.strftime('%Y-%m')
                            valor = float(get_value(t, 'Valor', 'valor', 'VALUE') or 0)
                            descricao = get_value(t, 'Descrição', 'Descricao', 'descricao', 'description') or ''
                            categoria = get_value(t, 'Categoria', 'categoria', 'category') or 'Importado'
                            tipo = get_value(t, 'Tipo', 'tipo', 'type') or 'SAIDA'
                            status = get_value(t, 'Status', 'status') or 'Pendente'
                            classificacao = get_value(t, 'Classificação', 'Classificacao', 'classificacao', 'classification') or 'Essenciais'
                            fixado = get_value(t, 'Fixado', 'fixado', 'fixed') or False
                            
                            # Converte fixado de 'Sim'/'Não' para boolean
                            if isinstance(fixado, str):
                                fixado = fixado.lower() in ['sim', 'yes', 'true', '1']
                            
                            # ✅ VERIFICA DUPLICATA: mesma data, descrição e valor
                            existing = Transaction.query.filter_by(
                                user_id=current_user.id,
                                data=data_obj,
                                descricao=descricao,
                                valor=valor
                            ).first()
                            
                            if existing:
                                duplicatas += 1
                                continue  # Pula registro duplicado
                            
                            # Cria nova transação
                            new_trans = Transaction(
                                user_id=current_user.id,
                                data=data_obj,
                                ano_mes=ano_mes,
                                categoria=categoria,
                                tipo=tipo.upper(),
                                descricao=descricao,
                                valor=valor,
                                status=status,
                                classificacao=classificacao,
                                fixado=fixado
                            )
                            db.session.add(new_trans)
                            contador_trans += 1
                            
                        except Exception as e:
                            print(f"⚠️ Erro ao importar transação: {e}")
                            print(f"   Dados: {t}")
                            continue  # Continua com próximo item
                
                # ========== RESTAURA DESPESAS FIXAS ==========
                if "fixed_expenses" in file_content:
                    for f in file_content["fixed_expenses"]:
                        try:
                            descricao = get_value(f, 'Descrição', 'Descricao', 'descricao', 'description') or ''
                            valor = float(get_value(f, 'Valor', 'valor', 'value') or 0)
                            dia_fixo = int(get_value(f, 'Dia_Fixo', 'dia_fixo', 'day') or 1)
                            tipo = get_value(f, 'Tipo', 'tipo', 'type') or 'SAIDA'
                            categoria = get_value(f, 'Categoria', 'categoria', 'category') or 'Fixo'
                            classificacao = get_value(f, 'Classificação', 'Classificacao', 'classificacao', 'classification') or 'Essenciais'
                            
                            # ✅ VERIFICA DUPLICATA: mesma descrição, valor e dia
                            existing = FixedExpense.query.filter_by(
                                user_id=current_user.id,
                                descricao=descricao,
                                valor=valor,
                                dia_fixo=dia_fixo
                            ).first()
                            
                            if existing:
                                duplicatas += 1
                                continue
                            
                            new_fixed = FixedExpense(
                                user_id=current_user.id,
                                tipo=tipo.upper(),
                                categoria=categoria,
                                descricao=descricao,
                                valor=valor,
                                dia_fixo=dia_fixo,
                                classificacao=classificacao
                            )
                            db.session.add(new_fixed)
                            contador_fixos += 1
                            
                        except Exception as e:
                            print(f"⚠️ Erro ao importar fixo: {e}")
                            print(f"   Dados: {f}")
                            continue
                
                # ========== RESTAURA METAS ==========
                if "goals" in file_content:
                    for g in file_content["goals"]:
                        try:
                            descricao = get_value(g, 'Descrição', 'Descricao', 'descricao', 'description') or ''
                            valor_alvo = float(get_value(g, 'Valor_Alvo', 'valor_alvo', 'target') or 0)
                            valor_atual = float(get_value(g, 'Valor_Atual', 'valor_atual', 'current') or 0)
                            
                            # ✅ VERIFICA DUPLICATA: mesma descrição
                            existing = Goal.query.filter_by(
                                user_id=current_user.id,
                                descricao=descricao
                            ).first()
                            
                            if existing:
                                duplicatas += 1
                                continue
                            
                            new_goal = Goal(
                                user_id=current_user.id,
                                descricao=descricao,
                                valor_alvo=valor_alvo,
                                valor_atual=valor_atual
                            )
                            db.session.add(new_goal)
                            contador_metas += 1
                            
                        except Exception as e:
                            print(f"⚠️ Erro ao importar meta: {e}")
                            print(f"   Dados: {g}")
                            continue
                
                # Salva tudo no banco de dados
                db.session.commit()
                
                # Mensagem de sucesso detalhada
                msg = f'✅ Backup restaurado! {contador_trans} transações, {contador_fixos} fixos, {contador_metas} metas importadas.'
                if duplicatas > 0:
                    msg += f' ({duplicatas} duplicatas ignoradas)'
                flash(msg, 'success')
            else:
                flash('❌ Formato de backup não reconhecido.', 'warning')
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro ao restaurar backup: {str(e)}', 'danger')
            print(f"Erro completo: {e}")
            import traceback
            traceback.print_exc()
            
    return redirect(url_for('dashboard'))

@app.route('/importar_planilha_generica', methods=['POST'])
@login_required
def importar_planilha_generica():
    """Importa planilha Excel"""
    if request.files.get('excel_file'):
        c = processar_importacao(request.files['excel_file'], current_user.id)
        if c > 0:
            flash(f'{c} lançamentos importados.', 'success')
        elif c == 0:
            flash('Nenhum lançamento novo encontrado.', 'warning')
        else:
            flash('Erro ao importar planilha.', 'danger')
    return redirect(url_for('dashboard'))


# ============================================
# ROTA TEMPORÁRIA - IMPORTAÇÃO DE BACKUP JSON ANTIGO
# ============================================

@app.route('/importar_backup_json_antigo')
@login_required
def importar_backup_json_antigo():
    """
    ROTA TEMPORÁRIA - Use apenas UMA VEZ para importar backup antigo
    Acesse: http://localhost:5000/importar_backup_json_antigo
    
    Importa dados do arquivo backup_completo_20251223.json para o banco SQL
    """
    import os
    
    # Caminho do arquivo de backup
    backup_file = 'backup_completo_20251223.json'
    
    if not os.path.exists(backup_file):
        flash(f'❌ Arquivo {backup_file} não encontrado neste diretório.', 'danger')
        return redirect(url_for('dashboard'))
    
    try:
        # Lê o arquivo JSON
        with open(backup_file, 'r', encoding='utf-8') as f:
            backup_data = json.load(f)
        
        contador_trans = 0
        contador_fixos = 0
        contador_metas = 0
        
        # ========== IMPORTA TRANSAÇÕES ==========
        if 'transactions' in backup_data:
            for t in backup_data['transactions']:
                try:
                    # Converte data
                    if isinstance(t.get('data'), str):
                        if 'T' in t['data']:  # ISO format
                            data_obj = datetime.fromisoformat(t['data'].replace('Z', '+00:00')).date()
                        elif '-' in t['data']:  # YYYY-MM-DD
                            data_obj = datetime.strptime(t['data'], '%Y-%m-%d').date()
                        else:  # DD/MM/YYYY
                            data_obj = datetime.strptime(t['data'], '%d/%m/%Y').date()
                    else:
                        data_obj = t['data']
                    
                    ano_mes = t.get('ano_mes', data_obj.strftime('%Y-%m'))
                    
                    # Verifica se já existe (evita duplicatas)
                    existing = Transaction.query.filter_by(
                        user_id=current_user.id,
                        data=data_obj,
                        descricao=t.get('descricao', ''),
                        valor=t.get('valor', 0)
                    ).first()
                    
                    if existing:
                        continue  # Pula duplicatas
                    
                    # Cria nova transação
                    new_trans = Transaction(
                        user_id=current_user.id,
                        data=data_obj,
                        ano_mes=ano_mes,
                        categoria=t.get('categoria', 'Importado'),
                        tipo=t.get('tipo', 'SAIDA'),
                        descricao=t.get('descricao', ''),
                        valor=float(t.get('valor', 0)),
                        status=t.get('status', 'Pendente'),
                        classificacao=t.get('classificacao', 'Essenciais'),
                        fixado=t.get('fixado', False)
                    )
                    db.session.add(new_trans)
                    contador_trans += 1
                    
                except Exception as e:
                    print(f"Erro ao importar transação: {e}")
                    continue
        
        # ========== IMPORTA DESPESAS FIXAS ==========
        if 'fixed_expenses' in backup_data:
            for f in backup_data['fixed_expenses']:
                try:
                    # Verifica se já existe
                    existing = FixedExpense.query.filter_by(
                        user_id=current_user.id,
                        descricao=f.get('descricao', ''),
                        valor=f.get('valor', 0),
                        dia_fixo=f.get('dia_fixo', 1)
                    ).first()
                    
                    if existing:
                        continue
                    
                    new_fixed = FixedExpense(
                        user_id=current_user.id,
                        tipo=f.get('tipo', 'SAIDA'),
                        categoria=f.get('categoria', 'Fixo'),
                        descricao=f.get('descricao', ''),
                        valor=float(f.get('valor', 0)),
                        dia_fixo=int(f.get('dia_fixo', 1)),
                        classificacao=f.get('classificacao', 'Essenciais')
                    )
                    db.session.add(new_fixed)
                    contador_fixos += 1
                    
                except Exception as e:
                    print(f"Erro ao importar fixo: {e}")
                    continue
        
        # ========== IMPORTA METAS ==========
        if 'goals' in backup_data:
            for g in backup_data['goals']:
                try:
                    # Verifica se já existe
                    existing = Goal.query.filter_by(
                        user_id=current_user.id,
                        descricao=g.get('descricao', '')
                    ).first()
                    
                    if existing:
                        continue
                    
                    new_goal = Goal(
                        user_id=current_user.id,
                        descricao=g.get('descricao', ''),
                        valor_alvo=float(g.get('valor_alvo', 0)),
                        valor_atual=float(g.get('valor_atual', 0))
                    )
                    db.session.add(new_goal)
                    contador_metas += 1
                    
                except Exception as e:
                    print(f"Erro ao importar meta: {e}")
                    continue
        
        # Salva tudo no banco
        db.session.commit()
        
        flash(f'✅ Importação concluída! {contador_trans} transações, {contador_fixos} fixos, {contador_metas} metas importadas.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro na importação: {str(e)}', 'danger')
    
    return redirect(url_for('dashboard'))


# ============================================
# ROTAS DE AUTENTICAÇÃO
# ============================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash('Login realizado com sucesso!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Usuário ou senha inválidos.', 'danger')
    
    return render_template('login.html', mode='login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Página de registro"""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')
        
        if len(username) < 3:
            flash('Nome de usuário deve ter pelo menos 3 caracteres.', 'danger')
        elif len(password) < 4:
            flash('Senha deve ter pelo menos 4 caracteres.', 'danger')
        elif password != confirm:
            flash('As senhas não conferem.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Este nome de usuário já está em uso.', 'danger')
        else:
            new_user = User(username=username)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Conta criada com sucesso! Faça login.', 'success')
            return redirect(url_for('login'))
    
    return render_template('login.html', mode='register')

@app.route('/logout')
@login_required
def logout():
    """Logout"""
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('login'))


# ============================================
# TEMPLATE DE LOGIN/REGISTRO
# ============================================
# Template movido para templates/login.html


# ============================================
# INICIALIZAÇÃO DO BANCO DE DADOS
# ============================================
def init_db():
    """Cria todas as tabelas do banco de dados e usuário admin padrão"""
    with app.app_context():
        db.create_all()
        print("✅ Banco de dados inicializado com sucesso!")
        
        # Cria usuário admin padrão se não existir
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("👤 Usuário 'admin' criado (senha: admin123)")
            print("⚠️  IMPORTANTE: Altere a senha após o primeiro login!")

if __name__ == '__main__':
    init_db()  # Cria as tabelas se não existirem
    print("\n🚀 Iniciando servidor Flask...")
    print("📝 Acesse: http://localhost:5000")
    print("👤 Login padrão: admin / admin123\n")
    app.run(debug=True, host='0.0.0.0', port=5000)