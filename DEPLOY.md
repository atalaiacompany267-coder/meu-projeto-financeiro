# 🚀 GUIA DE DEPLOY - Controle Financeiro

## 📦 Arquivos Criados para Deploy

✅ `requirements.txt` - Dependências Python  
✅ `gunicorn_config.py` - Configuração do servidor Gunicorn  
✅ `Procfile` - Comando de inicialização (Heroku/Render)  
✅ `runtime.txt` - Versão do Python

---

## 🌐 Deploy no Render

### 1. Prepare o Repositório Git

```bash
git init
git add .
git commit -m "Deploy: Sistema Financeiro Multi-usuário"
```

### 2. Crie Repositório no GitHub

```bash
# Crie um novo repositório no GitHub
# Depois conecte:
git remote add origin https://github.com/SEU_USUARIO/financeiro.git
git push -u origin main
```

### 3. Configure no Render

1. Acesse [render.com](https://render.com)
2. Clique em **"New +"** → **"Web Service"**
3. Conecte seu repositório GitHub
4. Configure:
   - **Name:** `financeiro-app`
   - **Environment:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn --config gunicorn_config.py projeto_clean:app`
   - **Instance Type:** `Free` (ou `Starter`)

### 4. Variáveis de Ambiente (Opcional)

No Render, vá em **Environment** e adicione:

```
SECRET_KEY=sua_chave_secreta_aleatoria_aqui
DATABASE_URL=sqlite:///financeiro.db
FLASK_ENV=production
```

### 5. Deploy Automático

- Render detectará automaticamente as configurações
- O deploy começará automaticamente
- Aguarde ~5 minutos para conclusão

---

## 🔧 Comandos Locais de Teste

### Testar com Gunicorn Localmente:

```bash
# Instale as dependências
pip install -r requirements.txt

# Rode com Gunicorn
gunicorn --config gunicorn_config.py projeto_clean:app

# Acesse: http://localhost:5000
```

### Teste sem Gunicorn (desenvolvimento):

```bash
python projeto_clean.py
```

---

## 🌍 Deploy em Outras Plataformas

### Heroku:

```bash
heroku login
heroku create financeiro-app
git push heroku main
heroku open
```

### Railway:

```bash
railway login
railway init
railway up
```

### DigitalOcean App Platform:

1. Conecte repositório GitHub
2. Use Build Command: `pip install -r requirements.txt`
3. Use Run Command: `gunicorn --config gunicorn_config.py projeto_clean:app`

---

## ⚙️ Configurações de Produção

### 1. **Troque a SECRET_KEY**

No `projeto_clean.py`, substitua:

```python
app.secret_key = 'chave_financeira_...'
```

Por:

```python
import os
app.secret_key = os.environ.get('SECRET_KEY', 'chave_fallback_apenas_dev')
```

### 2. **Use PostgreSQL em Produção**

Substitua:

```python
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///financeiro.db'
```

Por:

```python
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'sqlite:///financeiro.db'
).replace('postgres://', 'postgresql://')  # Fix Heroku
```

### 3. **Desabilite Debug Mode**

No final do `projeto_clean.py`:

```python
if __name__ == '__main__':
    init_db()
    # Remove debug=True em produção
    app.run(host='0.0.0.0', port=5000)
```

---

## 📊 Monitoramento

### Logs no Render:

```bash
# Acesse: Dashboard → Your Service → Logs
```

### Verificar Status:

```bash
curl https://seu-app.onrender.com
```

---

## 🔒 Segurança em Produção

✅ **HTTPS Automático** (Render fornece SSL gratuito)  
✅ **Senhas com Hash** (Werkzeug - já implementado)  
✅ **Sessões Seguras** (Flask-Login - já configurado)  
⚠️ **Troque SECRET_KEY** antes do deploy  
⚠️ **Use PostgreSQL** em vez de SQLite para produção

---

## 🎉 Pronto!

Seu aplicativo estará disponível em:
- **Render:** `https://financeiro-app.onrender.com`
- **Heroku:** `https://financeiro-app.herokuapp.com`
- **Railway:** `https://financeiro-app.railway.app`

**Primeiro acesso:** 
- Usuário: `admin`
- Senha: `admin123`

**⚠️ IMPORTANTE:** Crie seu próprio usuário e delete o admin após primeiro acesso!
