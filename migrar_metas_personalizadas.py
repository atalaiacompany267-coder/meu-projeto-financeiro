"""
Script de migração para adicionar colunas de metas personalizadas
Execute este script uma vez para adicionar as colunas meta_essencial, meta_estilo e meta_investimento
"""

from projeto_clean import app, db
from sqlalchemy import text

def adicionar_colunas_metas():
    """Adiciona as colunas de metas personalizadas na tabela users"""
    with app.app_context():
        try:
            # Tenta adicionar cada coluna individualmente
            # Se a coluna já existir, o erro será ignorado
            
            print("Adicionando coluna meta_essencial...")
            try:
                db.session.execute(text(
                    "ALTER TABLE users ADD COLUMN meta_essencial INTEGER NOT NULL DEFAULT 50"
                ))
                db.session.commit()
                print("✅ Coluna meta_essencial adicionada com sucesso!")
            except Exception as e:
                db.session.rollback()
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print("⚠️  Coluna meta_essencial já existe")
                else:
                    print(f"❌ Erro ao adicionar meta_essencial: {e}")
            
            print("\nAdicionando coluna meta_estilo...")
            try:
                db.session.execute(text(
                    "ALTER TABLE users ADD COLUMN meta_estilo INTEGER NOT NULL DEFAULT 30"
                ))
                db.session.commit()
                print("✅ Coluna meta_estilo adicionada com sucesso!")
            except Exception as e:
                db.session.rollback()
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print("⚠️  Coluna meta_estilo já existe")
                else:
                    print(f"❌ Erro ao adicionar meta_estilo: {e}")
            
            print("\nAdicionando coluna meta_investimento...")
            try:
                db.session.execute(text(
                    "ALTER TABLE users ADD COLUMN meta_investimento INTEGER NOT NULL DEFAULT 20"
                ))
                db.session.commit()
                print("✅ Coluna meta_investimento adicionada com sucesso!")
            except Exception as e:
                db.session.rollback()
                if "already exists" in str(e).lower() or "duplicate column" in str(e).lower():
                    print("⚠️  Coluna meta_investimento já existe")
                else:
                    print(f"❌ Erro ao adicionar meta_investimento: {e}")
            
            print("\n" + "="*60)
            print("MIGRAÇÃO CONCLUÍDA!")
            print("="*60)
            print("\nAs colunas de metas personalizadas foram adicionadas.")
            print("Você já pode usar o sistema de configurações.")
            
        except Exception as e:
            print(f"\n❌ Erro geral durante a migração: {e}")
            db.session.rollback()

if __name__ == "__main__":
    print("="*60)
    print("SCRIPT DE MIGRAÇÃO - METAS PERSONALIZADAS")
    print("="*60)
    print("\nEste script irá adicionar as seguintes colunas na tabela 'users':")
    print("  - meta_essencial (padrão: 50)")
    print("  - meta_estilo (padrão: 30)")
    print("  - meta_investimento (padrão: 20)")
    print("\n" + "="*60)
    
    input("\nPressione ENTER para continuar ou CTRL+C para cancelar...")
    
    adicionar_colunas_metas()
