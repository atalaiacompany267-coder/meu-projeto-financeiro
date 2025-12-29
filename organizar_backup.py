#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de Organização de Backup
Limpa a raiz do projeto movendo arquivos legados para pasta de backup
"""

import os
import shutil
from pathlib import Path

# Configurações
PASTA_BACKUP = "backup_antigo_seguranca"

# Arquivos para mover (relativos à raiz do projeto)
ARQUIVOS_PARA_MOVER = [
    # Documentação/Instruções
    "DEPLOY.md",
    "INSTRUCOES_BOOTSTRAP5.md",
    "INSTRUCOES_LOGIN.md",
    "PERSISTENCIA_ANO.md",
    
    # Dados legados (JSON/CSV)
    "lancamentos_fixos.json",
    "metas.json",
    "log_geracao_fixos.json",
    "users.json",
    
    # Scripts de migração
    "migrar_ano.py",
]

# Arquivos protegidos (NÃO devem ser movidos)
ARQUIVOS_PROTEGIDOS = [
    "projeto_clean.py",
    "organizar_backup.py",
    "gunicorn_config.py",
    "requirements.txt",
    "runtime.txt",
    "Procfile",
    "README.md",
]

def criar_pasta_backup():
    """Cria a pasta de backup se não existir"""
    if not os.path.exists(PASTA_BACKUP):
        os.makedirs(PASTA_BACKUP)
        print(f"✅ Pasta '{PASTA_BACKUP}' criada com sucesso!")
    else:
        print(f"ℹ️  Pasta '{PASTA_BACKUP}' já existe.")

def mover_arquivo(arquivo):
    """Move um arquivo para a pasta de backup"""
    # Verifica se o arquivo existe
    if not os.path.exists(arquivo):
        return False, f"Arquivo não encontrado: {arquivo}"
    
    # Verifica se é arquivo protegido
    if arquivo in ARQUIVOS_PROTEGIDOS:
        return False, f"Arquivo protegido (não movido): {arquivo}"
    
    try:
        destino = os.path.join(PASTA_BACKUP, arquivo)
        shutil.move(arquivo, destino)
        return True, f"✅ Movido: {arquivo} → {PASTA_BACKUP}/"
    except Exception as e:
        return False, f"❌ Erro ao mover {arquivo}: {str(e)}"

def buscar_csv_original():
    """Busca por arquivos CSV na raiz do projeto"""
    arquivos_csv = [f for f in os.listdir('.') if f.endswith('.csv')]
    return arquivos_csv

def main():
    """Função principal"""
    print("=" * 60)
    print("🗂️  SCRIPT DE ORGANIZAÇÃO DE BACKUP")
    print("=" * 60)
    print()
    
    # Mudar para o diretório do script
    script_dir = Path(__file__).parent.absolute()
    os.chdir(script_dir)
    print(f"📁 Diretório de trabalho: {script_dir}")
    print()
    
    # Criar pasta de backup
    criar_pasta_backup()
    print()
    
    # Buscar e adicionar arquivos CSV
    arquivos_csv = buscar_csv_original()
    if arquivos_csv:
        print(f"📊 Encontrados {len(arquivos_csv)} arquivo(s) CSV:")
        for csv in arquivos_csv:
            print(f"   - {csv}")
            ARQUIVOS_PARA_MOVER.append(csv)
        print()
    
    # Contadores
    movidos = []
    nao_encontrados = []
    erros = []
    
    # Processar cada arquivo
    print("📦 Movendo arquivos...")
    print("-" * 60)
    
    for arquivo in ARQUIVOS_PARA_MOVER:
        sucesso, mensagem = mover_arquivo(arquivo)
        print(mensagem)
        
        if sucesso:
            movidos.append(arquivo)
        elif "não encontrado" in mensagem.lower():
            nao_encontrados.append(arquivo)
        else:
            erros.append(arquivo)
    
    # Relatório final
    print()
    print("=" * 60)
    print("📊 RELATÓRIO FINAL")
    print("=" * 60)
    print()
    
    if movidos:
        print(f"✅ Arquivos movidos com sucesso ({len(movidos)}):")
        for arquivo in movidos:
            print(f"   ✓ {arquivo}")
        print()
    
    if nao_encontrados:
        print(f"ℹ️  Arquivos não encontrados ({len(nao_encontrados)}):")
        for arquivo in nao_encontrados:
            print(f"   • {arquivo}")
        print()
    
    if erros:
        print(f"❌ Erros ao mover ({len(erros)}):")
        for arquivo in erros:
            print(f"   ✗ {arquivo}")
        print()
    
    # Resumo
    print("-" * 60)
    print(f"📌 Total processado: {len(ARQUIVOS_PARA_MOVER)} arquivo(s)")
    print(f"   • Movidos: {len(movidos)}")
    print(f"   • Não encontrados: {len(nao_encontrados)}")
    print(f"   • Erros: {len(erros)}")
    print()
    
    if movidos:
        print("🎉 Limpeza concluída! A raiz do projeto está organizada.")
    else:
        print("⚠️  Nenhum arquivo foi movido.")
    
    print("=" * 60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Operação cancelada pelo usuário.")
    except Exception as e:
        print(f"\n\n❌ Erro inesperado: {str(e)}")
