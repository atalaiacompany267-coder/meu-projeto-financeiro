# 🔄 Persistência de Ano - Relatório Anual

## ✅ O que foi implementado:

### 1. **Nova Coluna no Banco de Dados**
- Adicionado campo `last_year_viewed` na tabela `users`
- Armazena o último ano visualizado pelo usuário

### 2. **Lógica de Persistência Inteligente**

A ordem de prioridade para determinar o ano exibido é:

1. **Ano selecionado manualmente** (via formulário)
2. **Ano salvo no banco de dados** (`last_year_viewed`)
3. **Ano salvo na sessão** (`session['last_year']`)
4. **Ano extraído do mês do Dashboard** (se `last_month_viewed = '2026-03'` → ano = 2026)
5. **Ano atual** (fallback padrão)

### 3. **Sincronização Bidirecional**

**Dashboard → Relatório Anual:**
- Quando você seleciona **Janeiro/2026** no Dashboard
- O sistema automaticamente atualiza `last_year_viewed = 2026`
- Ao navegar para Relatório Anual, ele já mostra **2026**

**Relatório Anual → Dashboard:**
- Quando você seleciona **2024** no Relatório Anual
- O sistema salva `last_year_viewed = 2024`
- Mas o Dashboard mantém o mês específico selecionado anteriormente

---

## 📝 Como executar a migração:

### **Passo 1: Executar o script de migração**

```bash
python migrar_ano.py
```

**O que o script faz:**
- ✅ Verifica se a coluna `last_year_viewed` já existe
- ✅ Se não existir, cria a coluna
- ✅ Sincroniza anos existentes dos meses salvos
  - Ex: Se `last_month_viewed = '2025-12'`, define `last_year_viewed = 2025`

### **Passo 2: Verificar no banco de dados** (opcional)

```sql
-- Ver estrutura da tabela
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'users';

-- Ver dados dos usuários
SELECT username, last_month_viewed, last_year_viewed 
FROM users;
```

---

## 🧪 Como testar:

### **Teste 1: Navegação Dashboard → Relatório**
1. No **Dashboard**, selecione **Março/2024**
2. Clique em **Relatório Anual** no menu lateral
3. ✅ **Resultado esperado:** Relatório carrega automaticamente com ano **2024**

### **Teste 2: Navegação Relatório → Dashboard**
1. No **Relatório Anual**, selecione ano **2023**
2. Clique em **Dashboard** no menu lateral
3. ✅ **Resultado esperado:** Dashboard mostra o último mês de **2023** que você visitou

### **Teste 3: Persistência após reload**
1. No **Relatório Anual**, selecione ano **2022**
2. Feche o navegador completamente
3. Abra novamente e faça login
4. Vá direto para **Relatório Anual**
5. ✅ **Resultado esperado:** Ano **2022** já está selecionado

### **Teste 4: Novo usuário**
1. Crie um novo usuário
2. Faça login pela primeira vez
3. Acesse **Relatório Anual**
4. ✅ **Resultado esperado:** Mostra o ano **atual** (2025)

---

## 🔧 Código implementado:

### **Modelo User (projeto_clean.py)**
```python
last_year_viewed = db.Column(db.Integer, nullable=True)  # Formato: YYYY
```

### **Dashboard (projeto_clean.py - linhas 565-576)**
```python
if arg_mes:
    filtro = arg_mes
    current_user.last_month_viewed = filtro
    # Sincroniza ano com o Relatório Anual
    try:
        ano_do_mes = int(filtro.split('-')[0])
        current_user.last_year_viewed = ano_do_mes
        session['last_year'] = ano_do_mes
    except:
        pass
    db.session.commit()
```

### **Relatório Anual (projeto_clean.py - linhas 938-969)**
```python
@app.route('/relatorio_anual')
@login_required
def relatorio_anual():
    hoje = datetime.now()
    session.permanent = True
    
    arg_ano = request.args.get('filtro_ano')
    if arg_ano:
        ano = int(arg_ano)
        current_user.last_year_viewed = ano
        db.session.commit()
        session['last_year'] = ano
    else:
        saved_db = current_user.last_year_viewed
        saved_sess = session.get('last_year')
        
        # Sincroniza com mês do Dashboard se necessário
        if not saved_db and not saved_sess and current_user.last_month_viewed:
            try:
                ano = int(current_user.last_month_viewed.split('-')[0])
            except:
                ano = hoje.year
        elif saved_db:
            ano = saved_db
        elif saved_sess:
            ano = saved_sess
        else:
            ano = hoje.year
```

---

## 🎯 Benefícios da implementação:

1. ✅ **Memória Persistente:** Sistema lembra sua escolha mesmo após fechar o navegador
2. ✅ **Sincronização Automática:** Dashboard e Relatório se comunicam
3. ✅ **Experiência Fluida:** Menos cliques, navegação mais intuitiva
4. ✅ **Banco de Dados:** Dados salvos permanentemente (não apenas sessão)
5. ✅ **Fallback Inteligente:** Sistema sempre tem um valor válido para exibir

---

## ⚠️ Importante:

- Execute `python migrar_ano.py` **APENAS UMA VEZ**
- Se executar múltiplas vezes, o script detecta que a coluna já existe e não faz nada
- A migração é **segura** e não afeta dados existentes
- Todos os anos são automaticamente extraídos dos meses já salvos

---

## 🐛 Troubleshooting:

**Problema:** Erro "column 'last_year_viewed' does not exist"
- **Solução:** Execute `python migrar_ano.py`

**Problema:** Relatório sempre mostra ano atual
- **Solução:** Verifique se a migração foi executada e se o banco está acessível

**Problema:** Sincronização não funciona
- **Solução:** Limpe as sessões: `session.clear()` ou faça logout/login

---

## 📚 Referências:

- **Campo no banco:** `users.last_year_viewed` (INTEGER)
- **Session key:** `session['last_year']`
- **Rota principal:** `/relatorio_anual`
- **Template:** `templates/relatorio.html`
