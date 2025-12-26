# 💰 Sistema de Controle Financeiro Pessoal (Flask + Pandas)

Este é um projeto desenvolvido em Python focado em gestão financeira pessoal inteligente e automatizada. O sistema permite o gerenciamento de entradas e saídas, controle de despesas fixas recorrentes e análise de fluxo de caixa mensal.

## 🚀 Funcionalidades Principais

* **Dashboard Interativo:** Visualização clara das finanças por mês (receitas vs. despesas).
* **Gestão de Lançamentos:** Adicionar, editar e excluir transações financeiras.
* **Automação de Despesas Fixas:** O sistema gera automaticamente os lançamentos mensais recorrentes (ex: Aluguel, Assinaturas), evitando digitação repetitiva.
* **Sistema de Login:** Autenticação segura com hash de senhas.
* **Persistência de Dados:** Utiliza Pandas para manipulação de dados e Excel/JSON para persistência (fácil portabilidade).
* **Backup e Restauração:** Funcionalidades integradas para garantir a segurança dos dados.

## 🛠️ Tecnologias Utilizadas

* **Linguagem:** Python 3.12+
* **Framework Web:** Flask
* **Análise de Dados:** Pandas
* **Frontend:** HTML5, Bootstrap 5 (Jinja2 Templates)
* **Segurança:** Werkzeug Security (Password Hashing)

## 📦 Como rodar o projeto

1.  **Clone o repositório:**
    ```bash
    git clone [https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git](https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git)
    cd SEU-REPOSITORIO
    ```

2.  **Crie um ambiente virtual e ative:**
    ```bash
    python -m venv venv
    # Windows:
    .\venv\Scripts\activate
    # Linux/Mac:
    source venv/bin/activate
    ```

3.  **Instale as dependências:**
    ```bash
    pip install flask pandas openpyxl xlsxwriter
    ```

4.  **Execute a aplicação:**
    ```bash
    python projeto.pyw.py
    ```
    O sistema estará disponível em `http://127.0.0.1:5000`.

## autor
Desenvolvido por [Seu Nome].
