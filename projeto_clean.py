import json
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from flask import Flask, request, redirect, url_for, flash, render_template_string, session, send_file
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
# CONFIGURAÇÃO DO BANCO DE DADOS
# ============================================
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financeiro.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

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

# --- HTML TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.6.0/jquery.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jquery.mask/1.14.16/jquery.mask.min.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f4f7f6; margin: 0; color: #333; transition: background-color 0.3s, color 0.3s; }
        .navbar { background: #2c3e50; color: #fff; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .brand { font-size: 1.2em; font-weight: bold; }
        .nav-links { display: flex; align-items: center; gap: 20px; }
        .nav-links a, .dropbtn { color: #ecf0f1; text-decoration: none; font-weight: bold; font-size: 0.9em; background: none; border: none; cursor: pointer; }
        .nav-links a:hover, .dropbtn:hover { color: #3498db; }
        .dropdown { position: relative; display: inline-block; }
        .dropbtn { background-color: transparent; color: #ecf0f1; padding: 0; font-size: 0.9em; border: none; cursor: pointer; font-weight: bold; font-family: inherit; }
        .dropdown-content { display: none; position: absolute; right: 0; background-color: #fff; min-width: 180px; box-shadow: 0 8px 16px rgba(0,0,0,0.2); z-index: 100; border-radius: 5px; overflow: hidden; text-align: left; }
        .dropdown-content a { color: #333 !important; padding: 12px 16px; text-decoration: none; display: block; margin: 0 !important; font-weight: normal !important; }
        .dropdown-content a:hover { background-color: #f1f1f1; color: #3498db !important; }
        .dropdown:hover .dropdown-content { display: block; }
        .btn-privacy { background: none; border: none; color: #ecf0f1; cursor: pointer; font-size: 1.1em; padding: 5px; transition: color 0.3s; }
        .btn-privacy:hover { color: #3498db; }
        .container { max-width: 1200px; margin: 30px auto; padding: 0 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: #fff; padding: 20px; border-radius: 10px; border-left: 5px solid; box-shadow: 0 2px 5px rgba(0,0,0,0.05); transition: background-color 0.3s; }
        .stat-title { font-size: 0.85em; color: #777; text-transform: uppercase; }
        .stat-value { font-size: 1.6em; font-weight: bold; margin-bottom: 5px; }
        .stat-trend { font-size: 0.8em; font-weight: bold; display: flex; justify-content: space-between; align-items: center; }
        .trend-up { color: #27ae60; } .trend-down { color: #c0392b; } .trend-neutral { color: #7f8c8d; }
        .stat-avg { font-size: 0.75em; color: #7f8c8d; background: #f0f0f0; padding: 2px 6px; border-radius: 4px; }
        .c-entrada { border-color: #27ae60; color: #27ae60; }
        .c-saida { border-color: #c0392b; color: #c0392b; }
        .c-saldo-pos { border-color: #2980b9; color: #2980b9; }
        .c-saldo-neg { border-color: #c0392b; color: #c0392b; }
        .analytics-grid { display: grid; grid-template-columns: 1fr 1.5fr; gap: 20px; margin-bottom: 30px; }
        .box, .table-container, .content-box { background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 20px; transition: background-color 0.3s; }
        .macro-summary { margin-top: 15px; padding-top: 15px; border-top: 1px solid #eee; }
        body.dark-mode .macro-summary { border-top: 1px solid #333; }
        .rule-bars .bar-item { margin-bottom: 8px; }
        .bar-label { display: flex; justify-content: space-between; font-size: 0.8em; margin-bottom: 2px; font-weight: bold; color: #555; }
        .progress-bg { background: #eee; height: 8px; border-radius: 4px; overflow: hidden; }
        .progress-fill { height: 100%; border-radius: 4px; transition: width 1s ease-in-out; }
        .tooltip-container { position: relative; cursor: help; }
        .tooltip-text { visibility: hidden; width: 250px; background-color: #2c3e50; color: #fff; text-align: center; border-radius: 6px; padding: 8px; position: absolute; z-index: 10; bottom: 125%; left: 50%; margin-left: -125px; opacity: 0; transition: opacity 0.3s; font-size: 0.85em; box-shadow: 0 5px 15px rgba(0,0,0,0.3); pointer-events: none; white-space: normal; line-height: 1.4; }
        .tooltip-container:hover .tooltip-text { visibility: visible; opacity: 1; }
        .tooltip-text::after { content: ""; position: absolute; top: 100%; left: 50%; margin-left: -5px; border-width: 5px; border-style: solid; border-color: #2c3e50 transparent transparent transparent; }
        @media(max-width: 900px) { .stats-grid, .stats-grid-4, .analytics-grid { grid-template-columns: 1fr; } }
        .input-row { display: flex; gap: 10px; flex-wrap: wrap; align-items: flex-end; }
        .form-group { flex: 1; min-width: 120px; }
        .form-control { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 5px; font-size: 1em; }
        .btn-black { background: #2c3e50; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-weight: bold; height: 42px; }
        .btn-delete { background: #e74c3c; color: white; border: none; padding: 8px 12px; border-radius: 5px; cursor: pointer; font-size: 0.8em; display: inline-block; text-decoration: none;}
        .btn-edit { background: #3498db; color: white; border: none; padding: 8px 12px; border-radius: 5px; cursor: pointer; font-size: 0.8em; display: inline-block; text-decoration: none; }
        .check-col { width: 50px; text-align: center; }
        .btn-round { width: 28px; height: 28px; border-radius: 50%; border: 2px solid #bdc3c7; background: #fff; color: transparent; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.2s; text-decoration: none; font-size: 0.8em; margin: 0 auto; }
        .btn-round:hover { border-color: #3498db; }
        .btn-round.pago { background-color: #009432 !important; border-color: #009432 !important; color: #ffffff !important; box-shadow: 0 0 8px rgba(0, 148, 50, 0.6); opacity: 1 !important;}
        .btn-pin { background: #7f8c8d; color: white; border: none; padding: 8px 12px; border-radius: 5px; cursor: pointer; font-size: 0.8em; display: inline-block; text-decoration: none; opacity: 0.4; transition: all 0.3s; }
        .btn-pin:hover { opacity: 0.8; }
        .btn-pin.fixado { background: #f39c12 !important; color: #ffffff !important; opacity: 1 !important; box-shadow: 0 0 8px rgba(243, 156, 18, 0.6); }
        table { width: 100%; min-width: 700px; border-collapse: collapse; }
        th { background: #f8f9fa; padding: 15px; text-align: left; font-size: 0.85em; color: #666; text-transform: uppercase; transition: background-color 0.3s, color 0.3s; }
        td { padding: 15px; border-bottom: 1px solid #eee; font-size: 0.95em; transition: border-color 0.3s; }
        .text-center { text-align: center; } .text-right { text-align: right; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; text-transform: uppercase; display: inline-block; min-width: 70px; text-align: center;}
        .badge-entrada { background-color: rgba(39, 174, 96, 0.2); color: #27ae60; border: 1px solid #27ae60; }
        .badge-saida { background-color: rgba(192, 57, 43, 0.2); color: #c0392b; border: 1px solid #c0392b; }
        .action-btns { white-space: nowrap; display: flex; gap: 8px; justify-content: center; }
        .filter-controls { display: flex; gap: 10px; margin-bottom: 15px; align-items: center; }
        .btn-filter { background: #f8f9fa; color: #555; border: 1px solid #ddd; padding: 8px 15px; border-radius: 5px; cursor: pointer; font-weight: bold; }
        .btn-filter.active { background: #3498db; color: white; border-color: #3498db; }
        .alert { padding: 15px; margin-bottom: 20px; border-radius: 8px; color: white; text-align: center; font-weight: bold; }
        .success { background: #27ae60; } .danger { background: #e74c3c; } .warning { background: #f39c12; }
        body.privacy-active .privacy-mask { color: transparent !important; text-shadow: 0 0 10px rgba(0,0,0,0.5) !important; user-select: none; cursor: default; }
        body.privacy-active canvas { filter: blur(5px); }
        body.dark-mode { background-color: #121212; color: #e0e0e0; }
        body.dark-mode .navbar { background: #1f1f1f; }
        body.dark-mode .stat-card, body.dark-mode .table-container, body.dark-mode .card, body.dark-mode .content-box { background-color: #1e1e1e; color: #e0e0e0; box-shadow: 0 2px 5px rgba(255,255,255,0.05); border-color: #333; }
        body.dark-mode .stat-avg { background: #333; color: #aaa; }
        body.dark-mode h2, body.dark-mode h3, body.dark-mode h4, body.dark-mode label, body.dark-mode .stat-title { color: #ccc !important; }
        body.dark-mode .form-control { background-color: #2d2d2d; border: 1px solid #444; color: #fff; }
        body.dark-mode th { background-color: #2d2d2d; color: #aaa; }
        body.dark-mode td { border-bottom: 1px solid #333; }
        body.dark-mode .btn-filter { background-color: #2d2d2d; border: 1px solid #444; color: #ccc; }
        body.dark-mode .btn-filter.active { background-color: #3498db; border-color: #3498db; color: #fff; }
        body.dark-mode .dropdown-content { background-color: #2d2d2d; }
        body.dark-mode .dropdown-content a { color: #e0e0e0 !important; }
        body.dark-mode .dropdown-content a:hover { background-color: #333; }
        body.dark-mode .bar-label span { color: #ccc; }
        body.dark-mode .progress-bg { background: #333; }
        body.dark-mode .btn-round { border-color: #555; background: #2d2d2d; }
        body.dark-mode .tooltip-text { background-color: #eee; color: #333; }
        body.dark-mode .tooltip-text::after { border-color: #eee transparent transparent transparent; }
        .row-pago { background-color: rgba(39, 174, 96, 0.1); }
        body.dark-mode .row-pago { background-color: rgba(39, 174, 96, 0.2); }
        .total-row { background-color: #eee; font-weight: bold; }
        body.dark-mode .total-row { background-color: #333; color: white; }
        
        /* ESTILOS ESPECÍFICOS DE METAS */
        .meta-card { margin-bottom: 20px; transition: transform 0.2s; }
        .meta-card:hover { transform: translateY(-5px); }
        .meta-progress { height: 20px; border-radius: 10px; background: #eee; overflow: hidden; margin: 15px 0; }
        body.dark-mode .meta-progress { background: #333; }
        .meta-bar { height: 100%; transition: width 1s; background: linear-gradient(90deg, #3498db, #2ecc71); }
        .meta-details { display: flex; justify-content: space-between; font-size: 0.9em; font-weight: bold; color: #666; }
        body.dark-mode .meta-details { color: #aaa; }
    </style>
</head>
<body>
    {% if mode == 'dashboard' %}
        <div class="navbar">
            <div class="brand">DASHBOARD <span>FINANCEIRO</span></div>
            <div class="nav-links">
                <button id="btn-privacy" class="btn-privacy"><i class="fas fa-eye"></i></button>
                <button id="btn-darkmode" class="btn-privacy"><i class="fas fa-moon"></i></button>
                <span style="border-right: 1px solid rgba(255,255,255,0.2); height: 20px; margin: 0 10px;"></span>
                <a href="{{ url_for('metas') }}"><i class="fas fa-bullseye"></i> METAS</a>
                <a href="{{ url_for('lancamentos_fixos') }}"><i class="fas fa-redo-alt"></i> FIXOS</a>
                <a href="{{ url_for('relatorio_anual') }}"><i class="fas fa-chart-bar"></i> ANUAL</a>
                <div class="dropdown">
                    <button class="dropbtn"><i class="fas fa-database"></i> BACKUP <i class="fas fa-caret-down"></i></button>
                    <div class="dropdown-content">
                        <a href="{{ url_for('gerar_fixos_cmd', mes=filtro_atual) }}" style="color:#27ae60!important"><i class="fas fa-sync"></i> Gerar Fixos Agora</a>
                        <a href="{{ url_for('backup_json') }}"><i class="fas fa-download"></i> Salvar Backup (Completo)</a>
                        <a href="#" onclick="document.getElementById('rest').click();"><i class="fas fa-upload"></i> Restaurar Backup</a>
                        <a href="#" onclick="document.getElementById('imp').click();" style="color:#27ae60!important"><i class="fas fa-file-excel"></i> Importar Excel</a>
                    </div>
                </div>
                <span style="border-right: 1px solid rgba(255,255,255,0.2); height: 20px; margin: 0 10px;"></span>
                <div class="dropdown">
                    <button class="dropbtn"><i class="fas fa-user"></i> {{ user }} <i class="fas fa-caret-down"></i></button>
                    <div class="dropdown-content">
                        <a href="{{ url_for('logout') }}" style="color:#e74c3c!important"><i class="fas fa-sign-out-alt"></i> Sair</a>
                    </div>
                </div>
                <form action="{{ url_for('restore_backup') }}" method="POST" enctype="multipart/form-data" style="display:none;"><input type="file" id="rest" name="backup_file" onchange="if(confirm('Restaurar Backup? Isso substituirá seus dados atuais.')){this.form.submit()}"></form>
                <form action="{{ url_for('importar_planilha_generica') }}" method="POST" enctype="multipart/form-data" style="display:none;"><input type="file" id="imp" name="excel_file" onchange="if(confirm('Importar?')){this.form.submit()}"></form>
            </div>
        </div>
        <div class="container">
            {% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for cat, msg in messages %}<div class="alert {{ cat }}">{{ msg }}</div>{% endfor %}{% endif %}{% endwith %}
            <div style="display:flex; justify-content:space-between; margin-bottom:20px;">
                <h2 style="margin:0; color:#2c3e50;">Movimentação - {{ mes_extenso }} {{ ano_extenso }}</h2>
                <form action="{{ url_for('dashboard') }}" method="GET" style="display:flex; gap:10px;">
                    <input type="month" name="filtro_mes" class="form-control" value="{{ filtro_atual }}" style="max-width:150px;">
                    <button class="btn-black" style="height:42px;"><i class="fas fa-filter"></i></button>
                </form>
            </div>
            <div class="stats-grid">
                <div class="stat-card c-entrada"><div class="stat-title">Entradas</div><div class="stat-value privacy-mask">R$ {{ "%.2f"|format(entrada) }}</div><div class="stat-trend"><span class="{{ 'trend-up' if trend_ent_pct>0 else 'trend-down' }}">{% if trend_ent_pct>0 %}<i class="fas fa-arrow-up"></i>{% elif trend_ent_pct<0 %}<i class="fas fa-arrow-down"></i>{% endif %} {{ "%.0f"|format(trend_ent_pct) }}%</span><span class="stat-avg privacy-mask">Méd: {{ "%.0f"|format(avg_ent) }}</span></div></div>
                <div class="stat-card c-saida"><div class="stat-title">Saídas</div><div class="stat-value privacy-mask">R$ {{ "%.2f"|format(saida) }}</div><div class="stat-trend"><span class="{{ 'trend-down' if trend_sai_pct>0 else 'trend-up' }}">{% if trend_sai_pct>0 %}<i class="fas fa-arrow-up"></i>{% elif trend_sai_pct<0 %}<i class="fas fa-arrow-down"></i>{% endif %} {{ "%.0f"|format(trend_sai_pct) }}%</span><span class="stat-avg privacy-mask">Méd: {{ "%.0f"|format(avg_sai) }}</span></div></div>
                <div class="stat-card {{ 'c-saldo-pos' if saldo>=0 else 'c-saldo-neg' }}"><div class="stat-title">Saldo</div><div class="stat-value privacy-mask">R$ {{ "%.2f"|format(saldo) }}</div></div>
            </div>
            
            <div class="analytics-grid">
                <div class="table-container">
                    <h3 style="margin-top:0; color:#2c3e50;">Categorias</h3>
                    <div style="height:250px;"><canvas id="expenseChart"></canvas></div>
                    <div class="macro-summary">
                        <div class="rule-bars">
                            {% set tot=entrada if entrada>0 else 1 %}
                            <div class="bar-item tooltip-container">
                                <div class="bar-label"><span>Essenciais (50%)</span><span class="privacy-mask">{{ "%.0f"|format((macro_vals['ESSENCIAIS']/tot)*100) }}%</span></div>
                                <div class="progress-bg"><div class="progress-fill" style="width:{{ (macro_vals['ESSENCIAIS']/tot)*100 }}%; background:#e74c3c;"></div></div>
                                <span class="tooltip-text"><b>Itens Inseridos:</b><br>{{ macro_tooltips['ESSENCIAIS'] }}</span>
                            </div>
                            <div class="bar-item tooltip-container">
                                <div class="bar-label"><span>Estilo (30%)</span><span class="privacy-mask">{{ "%.0f"|format((macro_vals['ESTILO_VIDA']/tot)*100) }}%</span></div>
                                <div class="progress-bg"><div class="progress-fill" style="width:{{ (macro_vals['ESTILO_VIDA']/tot)*100 }}%; background:#f39c12;"></div></div>
                                <span class="tooltip-text"><b>Itens Inseridos:</b><br>{{ macro_tooltips['ESTILO_VIDA'] }}</span>
                            </div>
                            <div class="bar-item tooltip-container">
                                <div class="bar-label"><span>Invest (20%)</span><span class="privacy-mask">{{ "%.0f"|format((macro_vals['INVESTIMENTOS']/tot)*100) }}%</span></div>
                                <div class="progress-bg"><div class="progress-fill" style="width:{{ (macro_vals['INVESTIMENTOS']/tot)*100 }}%; background:#27ae60;"></div></div>
                                <span class="tooltip-text"><b>Itens Inseridos:</b><br>{{ macro_tooltips['INVESTIMENTOS'] }}</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="table-container">
                    <h3 style="margin-top:0; color:#2c3e50;">Diário</h3>
                    <div style="height:340px;"><canvas id="dailyExpenseChart"></canvas></div>
                </div>
            </div>

            <div class="content-box">
                <h4 style="margin-top:0; color:#2c3e50;">Novo Lançamento ({{ hoje_br }})</h4>
                <form action="{{ url_for('add_lancamento') }}" method="POST">
                    <div class="input-row" style="margin-bottom:15px;">
                        <div class="form-group" style="flex:0 0 150px;"><label>Data</label><input name="data" class="form-control date-mask" value="{{ hoje_br }}" required></div>
                        <div class="form-group" style="flex:0 0 100px;"><label>Tipo</label><select name="tipo" class="form-control"><option value="SAIDA">Saída</option><option value="ENTRADA">Entrada</option></select></div>
                        <div class="form-group" style="flex:1;"><label>Categoria</label><input name="categoria" class="form-control" list="cat-opts" required placeholder="Ex: Mercado"><datalist id="cat-opts">{% for c in all_categories %}<option value="{{ c }}">{% endfor %}</datalist></div>
                        <div class="form-group" style="flex:1;"><label>Classificação</label><select name="classificacao" class="form-control"><option value="Essenciais">Essenciais</option><option value="Estilo de Vida">Estilo</option><option value="Investimentos">Invest</option></select></div>
                    </div>
                    <div class="input-row" style="margin-bottom:20px;">
                        <div class="form-group" style="flex:2;"><label>Descrição</label><input name="descricao" class="form-control"></div>
                        <div class="form-group" style="flex:1;"><label>Valor</label><input type="number" step="0.01" name="valor" class="form-control" required></div>
                        <div class="form-group" style="flex:0 0 150px;"><label>&nbsp;</label><button class="btn-black" style="width:100%; height:42px;">Adicionar</button></div>
                    </div>
                </form>
            </div>

            <div class="table-container">
                <div class="filter-controls">
                    <input id="search-input" class="form-control" placeholder="Buscar..." style="width:100%;">
                    <button class="btn-filter active" data-filter="all">Tudo</button><button class="btn-filter" data-filter="ENTRADA">Ent</button><button class="btn-filter" data-filter="SAIDA">Sai</button>
                </div>
                <div style="overflow-x:auto;">
                    <table id="lancamentos-table">
                        <thead><tr><th class="check-col"><i class="fas fa-check-circle"></i></th><th>Data</th><th>Tipo</th><th>Cat</th><th>Desc</th><th style="text-align:right;">Valor</th><th style="text-align:center;">Ações</th></tr></thead>
                        <tbody>
                            {% for l in dados_exibicao %}
                            <tr class="{% if l.Status=='Pago' %}row-pago{% endif %}" data-tipo="{{ l.Tipo }}" data-categoria="{{ l.Categoria|lower }}" data-descricao="{{ l.Descrição|lower }}">
                                <td class="check-col"><a href="{{ url_for('toggle_status', id=l.ID, filtro_mes=filtro_atual) }}" class="btn-round {% if l.Status=='Pago' %}pago{% endif %}"><i class="fas fa-check"></i></a></td>
                                <td>{{ l.Data }}</td>
                                <td><span style="color:{% if l.Tipo=='ENTRADA' %}#27ae60{% else %}#c0392b{% endif %}"><b>{{ l.Tipo }}</b></span></td>
                                <td>{{ l.Categoria }}</td><td>{{ l.Descrição }}</td>
                                <td class="privacy-mask" style="text-align:right; font-weight:bold;">R$ {{ "%.2f"|format(l.Valor|abs) }}</td>
                                <td class="action-btns">
                                    <a href="{{ url_for('pin_lancamento', lancamento_id=l.ID, filtro_mes=filtro_atual) }}" class="btn-pin {% if l.Fixado=='Sim' %}fixado{% endif %}"><i class="fas fa-thumbtack"></i></a>
                                    <a href="{{ url_for('edit_lancamento_form', lancamento_id=l.ID, filtro_mes=filtro_atual) }}" class="btn-edit"><i class="fas fa-edit"></i></a>
                                    <a href="{{ url_for('delete_lancamento', lancamento_id=l.ID, filtro_mes=filtro_atual) }}" class="btn-delete" onclick="return confirm('Excluir?')"><i class="fas fa-trash"></i></a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        {% if ask_to_generate %}
        <script>
            window.onload = function() {
                if(confirm('Deseja lançar as despesas fixas para este mês (' + '{{ mes_extenso }}' + ')?')) {
                    window.location.href = "{{ url_for('gerar_fixos_cmd', mes=filtro_atual) }}";
                }
            }
        </script>
        {% endif %}
        
        <script>
            document.addEventListener('DOMContentLoaded', () => {
                const body = document.body;
                if(localStorage.getItem('isPrivacyActive')==='true') body.classList.add('privacy-active');
                if(localStorage.getItem('isDarkMode')==='true') body.classList.add('dark-mode');
                document.getElementById('btn-privacy').onclick=()=>{body.classList.toggle('privacy-active');localStorage.setItem('isPrivacyActive',body.classList.contains('privacy-active'))};
                document.getElementById('btn-darkmode').onclick=()=>{body.classList.toggle('dark-mode');localStorage.setItem('isDarkMode',body.classList.contains('dark-mode'))};
                if(document.getElementById('expenseChart')) new Chart(document.getElementById('expenseChart').getContext('2d'), {type:'doughnut',data:{labels:{{ chart_cats|safe }},datasets:[{data:{{ chart_vals|safe }},backgroundColor:['#e74c3c','#3498db','#2ecc71','#f1c40f','#9b59b6','#34495e']}]},options:{maintainAspectRatio:false,plugins:{legend:{position:'right'}}}});
                if(document.getElementById('dailyExpenseChart')) new Chart(document.getElementById('dailyExpenseChart').getContext('2d'), {type:'bar',data:{labels:{{ chart_days|safe }},datasets:[{label:'Ent',data:{{ chart_daily_in|safe }},backgroundColor:'#27ae60'},{label:'Sai',data:{{ chart_daily_out|safe }},backgroundColor:'#c0392b'},{label:'Sobra',data:{{ chart_daily_bal|safe }},backgroundColor:'#2980b9'}]},options:{maintainAspectRatio:false}});
                if(typeof $.mask!=='undefined') $('.date-mask').mask('00/00/0000');
                const table = document.getElementById('lancamentos-table');
                const inp = document.getElementById('search-input');
                const btns = document.querySelectorAll('.btn-filter');
                let filter='all';
                const rows = table ? Array.from(table.querySelectorAll('tbody tr')) : [];
                const runFilter = () => {
                    const txt = inp.value.toLowerCase();
                    rows.forEach(r => {
                        const t = r.dataset.tipo;
                        const match = (r.dataset.descricao.includes(txt) || r.dataset.categoria.includes(txt)) && (filter==='all' || t===filter);
                        r.style.display = match ? '' : 'none';
                    });
                };
                btns.forEach(b => b.onclick = () => { btns.forEach(x=>x.classList.remove('active')); b.classList.add('active'); filter=b.dataset.filter; runFilter(); });
                inp.onkeyup = runFilter;
            });
        </script>
    {% endif %}

    {% if mode == 'edit_form' %}
        <div class="navbar"><div class="brand">EDITAR</div><div class="nav-links"><a href="{{ url_for('dashboard', filtro_mes=request.args.get('filtro_mes', '')) }}">VOLTAR</a></div></div>
        <div class="container" style="max-width:700px;">
            <div class="content-box">
                <h3 style="margin-top:0; color:#2c3e50;">Editar Lançamento #{{ lancamento.ID }}</h3>
                <form action="{{ url_for('edit_lancamento_save') }}" method="POST">
                    <input type="hidden" name="lancamento_id" value="{{ lancamento.ID }}">
                    <input type="hidden" name="filtro_mes_origem" value="{{ request.args.get('filtro_mes', '') }}">
                    <div class="input-row" style="margin-bottom:15px;">
                        <div class="form-group" style="flex:0 0 150px;"><label>Data</label><input name="data" class="form-control date-mask" value="{{ lancamento.Data }}" required></div>
                        <div class="form-group" style="flex:0 0 100px;"><label>Tipo</label><select name="tipo" class="form-control"><option value="SAIDA" {% if lancamento.Tipo=='SAIDA' %}selected{% endif %}>Saída</option><option value="ENTRADA" {% if lancamento.Tipo=='ENTRADA' %}selected{% endif %}>Entrada</option></select></div>
                        <div class="form-group" style="flex:1;"><label>Categoria</label><input name="categoria" class="form-control" value="{{ lancamento.Categoria }}" required></div>
                        <div class="form-group" style="flex:1;"><label>Classificação</label><select name="classificacao" class="form-control"><option value="Essenciais" {% if lancamento.Classificação=='Essenciais' %}selected{% endif %}>Essenciais</option><option value="Estilo de Vida" {% if lancamento.Classificação=='Estilo de Vida' %}selected{% endif %}>Estilo</option><option value="Investimentos" {% if lancamento.Classificação=='Investimentos' %}selected{% endif %}>Invest</option></select></div>
                    </div>
                    <div class="input-row" style="margin-bottom:20px;">
                        <div class="form-group" style="flex:2;"><label>Descrição</label><input name="descricao" class="form-control" value="{{ lancamento.Descrição }}"></div>
                        <div class="form-group" style="flex:1;"><label>Valor</label><input type="number" step="0.01" name="valor" class="form-control" value="{{ '%.2f'|format(lancamento.Valor|abs) }}"></div>
                    </div>
                    <button class="btn-black" style="width:100%; height:45px;">SALVAR EDIÇÃO</button>
                </form>
            </div>
            <script>if(typeof $.mask!=='undefined') $('.date-mask').mask('00/00/0000');</script>
        </div>
    {% endif %}

    {% if mode == 'lancamentos_fixos' %}
        <div class="navbar"><div class="brand">FIXOS</div><div class="nav-links"><button id="btn-privacy" class="btn-privacy"><i class="fas fa-eye"></i></button><a href="{{ url_for('dashboard') }}">VOLTAR</a></div></div>
        <div class="container">
            <div class="content-box">
                <h4 style="margin-top:0; color:#2c3e50;">Novo Lançamento Fixo</h4>
                <form action="{{ url_for('add_fixo') }}" method="POST">
                    <div class="input-row" style="margin-bottom:15px;">
                        <div class="form-group" style="flex:0 0 120px;"><label>Tipo</label><select name="tipo" class="form-control"><option value="SAIDA">Saída</option><option value="ENTRADA">Entrada</option></select></div>
                        <div class="form-group" style="flex:1;"><label>Categoria</label><input name="categoria" class="form-control" list="cat-opts" required placeholder="Categoria"><datalist id="cat-opts">{% for c in categorias_orcamento %}<option value="{{ c }}">{% endfor %}</datalist></div>
                        <div class="form-group" style="flex:1;"><label>Classificação</label><select name="classificacao" class="form-control"><option value="Essenciais">Essenciais</option><option value="Estilo de Vida">Estilo</option><option value="Investimentos">Invest</option></select></div>
                    </div>
                    <div class="input-row" style="margin-bottom:20px;">
                        <div class="form-group" style="flex:2;"><label>Descrição</label><input name="descricao" class="form-control" placeholder="Descrição"></div>
                        <div class="form-group" style="flex:1;"><label>Valor (R$)</label><input type="number" step="0.01" name="valor" class="form-control" placeholder="0.00" required></div>
                        <div class="form-group" style="flex:0 0 100px;"><label>Dia Fixo</label><input type="number" name="dia_fixo" class="form-control" placeholder="Dia" min="1" max="31" required></div>
                        <div class="form-group" style="flex:0 0 150px;"><label>&nbsp;</label><button class="btn-black" style="width:100%; height:42px;">ADICIONAR</button></div>
                    </div>
                </form>
            </div>
            <div class="table-container">
                <h4 style="margin-top:0; color:#2c3e50;">Lançamentos Fixos Cadastrados</h4>
                <div style="overflow-x:auto;">
                    <table>
                        <thead>
                            <tr>
                                <th class="text-center">Dia</th>
                                <th class="text-center">Tipo</th>
                                <th>Cat</th>
                                <th>Desc</th>
                                <th class="text-right">Valor</th>
                                <th class="text-center">Ação</th>
                            </tr>
                        </thead>
                        <tbody>
                            {% for id, e in fixed_entries %}
                            <tr>
                                <td class="text-center">{{ e.dia_fixo }}</td>
                                <td class="text-center"><span class="badge {% if e.tipo == 'ENTRADA' %}badge-entrada{% else %}badge-saida{% endif %}">{{ e.tipo }}</span></td>
                                <td>{{ e.categoria }}</td>
                                <td>{{ e.descricao }}</td>
                                <td class="privacy-mask text-right" style="font-weight:bold;">R$ {{ "%.2f"|format(e.valor) }}</td>
                                <td class="action-btns">
                                    <a href="{{ url_for('edit_fixo_form', id=id) }}" class="btn-edit"><i class="fas fa-edit"></i></a> 
                                    <a href="{{ url_for('delete_fixo', id=id) }}" class="btn-delete"><i class="fas fa-trash"></i></a>
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        <script>
            document.addEventListener('DOMContentLoaded', () => {
                const body = document.body;
                if(localStorage.getItem('isPrivacyActive')==='true') body.classList.add('privacy-active');
                if(localStorage.getItem('isDarkMode')==='true') body.classList.add('dark-mode');
                document.getElementById('btn-privacy').onclick=()=>{body.classList.toggle('privacy-active');localStorage.setItem('isPrivacyActive',body.classList.contains('privacy-active'))};
            });
        </script>
    {% endif %}

    {% if mode == 'edit_fixed_form' %}
        <div class="navbar"><div class="brand">EDITAR FIXO</div><div class="nav-links"><a href="{{ url_for('lancamentos_fixos') }}">VOLTAR</a></div></div>
        <div class="container" style="max-width:700px;">
            <div class="content-box">
                <h3 style="margin-top:0; color:#2c3e50;">Editar Fixo</h3>
                <form action="{{ url_for('edit_fixo_save', id=fixo_id) }}" method="POST">
                    <div class="input-row" style="margin-bottom:15px;">
                        <div class="form-group" style="flex:0 0 120px;"><label>Tipo</label><select name="tipo" class="form-control"><option value="SAIDA" {% if lancamento_fixo.tipo=='SAIDA' %}selected{% endif %}>Saída</option><option value="ENTRADA" {% if lancamento_fixo.tipo=='ENTRADA' %}selected{% endif %}>Entrada</option></select></div>
                        <div class="form-group" style="flex:1;"><label>Categoria</label><input name="categoria" class="form-control" value="{{ lancamento_fixo.categoria }}" required></div>
                        <div class="form-group" style="flex:1;"><label>Classificação</label><select name="classificacao" class="form-control"><option value="Essenciais" {% if lancamento_fixo.classificacao=='Essenciais' %}selected{% endif %}>Essenciais</option><option value="Estilo de Vida" {% if lancamento_fixo.classificacao=='Estilo de Vida' %}selected{% endif %}>Estilo</option><option value="Investimentos" {% if lancamento_fixo.classificacao=='Investimentos' %}selected{% endif %}>Invest</option></select></div>
                    </div>
                    <div class="input-row" style="margin-bottom:20px;">
                        <div class="form-group" style="flex:2;"><label>Descrição</label><input name="descricao" class="form-control" value="{{ lancamento_fixo.descricao }}"></div>
                        <div class="form-group" style="flex:1;"><label>Valor</label><input type="number" step="0.01" name="valor" class="form-control" value="{{ '%.2f'|format(lancamento_fixo.valor) }}"></div>
                        <div class="form-group" style="flex:0 0 100px;"><label>Dia</label><input type="number" name="dia_fixo" class="form-control" value="{{ lancamento_fixo.dia_fixo }}"></div>
                    </div>
                    <button class="btn-black" style="width:100%; height:45px;">SALVAR</button>
                </form>
            </div>
        </div>
    {% endif %}

    {% if mode == 'metas' %}
        <div class="navbar"><div class="brand">METAS & OBJETIVOS</div><div class="nav-links"><button id="btn-privacy" class="btn-privacy"><i class="fas fa-eye"></i></button><a href="{{ url_for('dashboard') }}">VOLTAR</a></div></div>
        <div class="container">
            <div class="content-box">
                <h4 style="margin-top:0; color:#2c3e50;">Nova Meta</h4>
                <form action="{{ url_for('add_meta') }}" method="POST">
                    <div class="input-row">
                        <div class="form-group" style="flex:2;"><label>Nome da Meta (Ex: Carro Novo)</label><input name="descricao" class="form-control" required></div>
                        <div class="form-group" style="flex:1;"><label>Valor Alvo (R$)</label><input type="number" step="0.01" name="valor_alvo" class="form-control" required></div>
                        <div class="form-group" style="flex:1;"><label>Já guardado (R$)</label><input type="number" step="0.01" name="valor_atual" class="form-control" value="0"></div>
                        <div class="form-group" style="flex:0 0 120px;"><label>&nbsp;</label><button class="btn-black" style="width:100%; height:42px;">CRIAR</button></div>
                    </div>
                </form>
            </div>
            
            <div class="stats-grid">
                {% for id, m in metas %}
                <div class="stat-card meta-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div class="stat-title">{{ m.descricao }}</div>
                        <div>
                            <a href="#" onclick="document.getElementById('add_val_id').value='{{ id }}'; document.getElementById('addValModal').style.display='block';" style="color:#27ae60; margin-right:10px;"><i class="fas fa-plus-circle"></i> Add</a>
                            <a href="{{ url_for('delete_meta', id=id) }}" style="color:#c0392b;" onclick="return confirm('Excluir meta?')"><i class="fas fa-trash"></i></a>
                        </div>
                    </div>
                    <div class="meta-progress">
                        <div class="meta-bar" style="width: {{ (m.valor_atual / m.valor_alvo * 100)|round }}%"></div>
                    </div>
                    <div class="meta-details">
                        <span class="privacy-mask">R$ {{ "%.2f"|format(m.valor_atual) }}</span>
                        <span>{{ (m.valor_atual / m.valor_alvo * 100)|round }}%</span>
                        <span class="privacy-mask">Meta: R$ {{ "%.2f"|format(m.valor_alvo) }}</span>
                    </div>
                </div>
                {% else %}
                <p style="text-align:center; color:#999; grid-column:span 3;">Nenhuma meta cadastrada ainda.</p>
                {% endfor %}
            </div>
        </div>
        
        <div id="addValModal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.5); z-index:1000;">
            <div style="background:white; margin:100px auto; padding:20px; width:300px; border-radius:10px;">
                <h4>Adicionar Valor</h4>
                <form action="{{ url_for('add_valor_meta') }}" method="POST">
                    <input type="hidden" name="meta_id" id="add_val_id">
                    <input type="number" step="0.01" name="valor" class="form-control" placeholder="Quanto guardou hoje?" required style="margin-bottom:15px;">
                    <button class="btn-black" style="width:100%;">Salvar</button>
                    <button type="button" onclick="document.getElementById('addValModal').style.display='none'" style="width:100%; margin-top:10px; background:none; border:none; color:#777; cursor:pointer;">Cancelar</button>
                </form>
            </div>
        </div>
        <script>
            document.addEventListener('DOMContentLoaded', () => {
                const body = document.body;
                if(localStorage.getItem('isPrivacyActive')==='true') body.classList.add('privacy-active');
                if(localStorage.getItem('isDarkMode')==='true') body.classList.add('dark-mode');
                document.getElementById('btn-privacy').onclick=()=>{body.classList.toggle('privacy-active');localStorage.setItem('isPrivacyActive',body.classList.contains('privacy-active'))};
            });
        </script>
    {% endif %}

    {% if mode == 'relatorio_anual' %}
        <div class="navbar"><div class="brand">ANUAL</div><div class="nav-links"><button id="btn-privacy" class="btn-privacy"><i class="fas fa-eye"></i></button><a href="{{ url_for('dashboard') }}">VOLTAR</a></div></div>
        <div class="container">
            <div style="margin-bottom:20px; text-align:right;"><form action="{{ url_for('relatorio_anual') }}" method="GET"><input type="number" name="filtro_ano" value="{{ ano_atual }}" class="form-control" style="width:100px; display:inline-block;"><button class="btn-black"><i class="fas fa-filter"></i></button></form></div>
            <div class="analytics-grid" style="grid-template-columns:1fr;"><div class="table-container"><h3>Gráfico</h3><div style="height:350px;"><canvas id="anChart"></canvas></div></div><div class="table-container"><h3>Dados</h3><div style="overflow-x:auto;"><table class="annual-table"><thead><tr><th>Mês</th><th>Entrada</th><th>Saída</th><th>Saldo</th></tr></thead><tbody>{% for r in relatorio_anual_data %}<tr><td>{{ r.Periodo }}</td><td class="privacy-mask" style="color:#27ae60;">R$ {{ "%.2f"|format(r.Entrada) }}</td><td class="privacy-mask" style="color:#c0392b;">R$ {{ "%.2f"|format(r.Saida) }}</td><td class="privacy-mask" style="font-weight:bold;">R$ {{ "%.2f"|format(r.Saldo) }}</td></tr>{% endfor %}<tr class="total-row"><td>TOTAL</td><td class="privacy-mask">R$ {{ "%.2f"|format(total_entrada) }}</td><td class="privacy-mask">R$ {{ "%.2f"|format(total_saida) }}</td><td class="privacy-mask">R$ {{ "%.2f"|format(total_saldo) }}</td></tr></tbody></table></div></div></div>
            <script>
                document.addEventListener('DOMContentLoaded', () => {
                    const body = document.body;
                    if(localStorage.getItem('isPrivacyActive')==='true') body.classList.add('privacy-active');
                    if(localStorage.getItem('isDarkMode')==='true') body.classList.add('dark-mode');
                    document.getElementById('btn-privacy').onclick=()=>{body.classList.toggle('privacy-active');localStorage.setItem('isPrivacyActive',body.classList.contains('privacy-active'))};
                    new Chart(document.getElementById('anChart').getContext('2d'), {type:'bar',data:{labels:{{ chart_labels|safe }},datasets:[{label:'Entrada',data:{{ chart_entrada|safe }},backgroundColor:'#27ae60'},{label:'Saída',data:{{ chart_saida|safe }},backgroundColor:'#c0392b'},{label:'Saldo',data:{{ chart_saldo|safe }},backgroundColor:'#2980b9'}]},options:{maintainAspectRatio:false}});
                });
            </script>
        </div>
    {% endif %}
</body>
</html>
"""

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
    
    return render_template_string(HTML_TEMPLATE, title="Dashboard", mode='dashboard', user=current_user.username, entrada=ent, saida=sai, saldo=sal, dados_exibicao=dados, chart_cats=json.dumps(cats), chart_vals=json.dumps(vals), chart_days=json.dumps(days), chart_daily_in=json.dumps(d_in), chart_daily_out=json.dumps(d_out), chart_daily_bal=json.dumps(d_bal), filtro_atual=filtro, mes_extenso=mes_ext, ano_extenso=ano_ext, hoje_br=hoje.strftime('%d/%m/%Y'), all_categories=get_all_categories(user_id), trend_ent_pct=t_ent, trend_sai_pct=t_sai, macro_vals=macro, avg_ent=avg_ent, avg_sai=avg_sai, macro_tooltips=tooltips, ask_to_generate=ask_to_generate)

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
    return render_template_string(HTML_TEMPLATE, title="Editar", mode='edit_form', lancamento=lancamento, categorias_orcamento=get_all_categories(current_user.id))

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
    
    return render_template_string(HTML_TEMPLATE, title="Fixos", mode='lancamentos_fixos', fixed_entries=fixed_entries, categorias_orcamento=get_all_categories(current_user.id))

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
    return render_template_string(HTML_TEMPLATE, title="Editar Fixo", mode='edit_fixed_form', fixo_id=id, lancamento_fixo=lancamento_fixo, categorias_orcamento=get_all_categories(current_user.id))

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
    
    return render_template_string(HTML_TEMPLATE, title="Metas", mode='metas', metas=metas_list)

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
    return render_template_string(HTML_TEMPLATE, title="Anual", mode='relatorio_anual', ano_atual=ano, relatorio_anual_data=res, total_entrada=te, total_saida=ts, total_saldo=tsal, chart_labels=json.dumps(lbs), chart_entrada=json.dumps(e), chart_saida=json.dumps(s), chart_saldo=json.dumps(sl))

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
    
    return render_template_string(LOGIN_TEMPLATE, mode='login')

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
    
    return render_template_string(LOGIN_TEMPLATE, mode='register')

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
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-br">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ 'Login' if mode == 'login' else 'Registro' }} - Controle Financeiro</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #2c3e50 0%, #3498db 100%); min-height: 100vh; display: flex; align-items: center; justify-content: center; }
        .login-container { background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 40px rgba(0,0,0,0.2); width: 100%; max-width: 400px; }
        .login-header { text-align: center; margin-bottom: 30px; }
        .login-header h1 { color: #2c3e50; font-size: 1.8em; margin-bottom: 10px; }
        .login-header p { color: #7f8c8d; }
        .form-group { margin-bottom: 20px; }
        .form-group label { display: block; margin-bottom: 8px; color: #2c3e50; font-weight: 600; }
        .form-control { width: 100%; padding: 12px 15px; border: 2px solid #eee; border-radius: 8px; font-size: 1em; transition: border-color 0.3s; }
        .form-control:focus { outline: none; border-color: #3498db; }
        .btn-primary { width: 100%; padding: 14px; background: #2c3e50; color: white; border: none; border-radius: 8px; font-size: 1.1em; font-weight: bold; cursor: pointer; transition: background 0.3s; }
        .btn-primary:hover { background: #34495e; }
        .alert { padding: 12px 15px; border-radius: 8px; margin-bottom: 20px; text-align: center; }
        .alert.success { background: #d4edda; color: #155724; }
        .alert.danger { background: #f8d7da; color: #721c24; }
        .alert.warning { background: #fff3cd; color: #856404; }
        .alert.info { background: #d1ecf1; color: #0c5460; }
        .login-footer { text-align: center; margin-top: 20px; }
        .login-footer a { color: #3498db; text-decoration: none; font-weight: 600; }
        .login-footer a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1><i class="fas fa-wallet"></i> Controle Financeiro</h1>
            <p>{{ 'Acesse sua conta' if mode == 'login' else 'Crie sua conta' }}</p>
        </div>
        
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for cat, msg in messages %}
                    <div class="alert {{ cat }}">{{ msg }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% if mode == 'login' %}
        <form method="POST">
            <div class="form-group">
                <label><i class="fas fa-user"></i> Usuário</label>
                <input type="text" name="username" class="form-control" required autofocus>
            </div>
            <div class="form-group">
                <label><i class="fas fa-lock"></i> Senha</label>
                <input type="password" name="password" class="form-control" required>
            </div>
            <button type="submit" class="btn-primary">Entrar</button>
        </form>
        <div class="login-footer">
            <p>Não tem conta? <a href="{{ url_for('register') }}">Registre-se</a></p>
        </div>
        {% else %}
        <form method="POST">
            <div class="form-group">
                <label><i class="fas fa-user"></i> Usuário</label>
                <input type="text" name="username" class="form-control" required autofocus>
            </div>
            <div class="form-group">
                <label><i class="fas fa-lock"></i> Senha</label>
                <input type="password" name="password" class="form-control" required>
            </div>
            <div class="form-group">
                <label><i class="fas fa-lock"></i> Confirmar Senha</label>
                <input type="password" name="confirm" class="form-control" required>
            </div>
            <button type="submit" class="btn-primary">Criar Conta</button>
        </form>
        <div class="login-footer">
            <p>Já tem conta? <a href="{{ url_for('login') }}">Faça login</a></p>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""


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