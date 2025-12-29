"""
Migração: Adicionar coluna last_year_viewed na tabela users

Execute este script UMA VEZ para adicionar a nova coluna ao banco de dados:
python migrar_ano.py
"""

import os
from sqlalchemy import create_engine, text

# Usar a mesma URL do banco de dados do projeto
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://neondb_owner:npg_NA4wBru6LHOZ@ep-jolly-lab-ahhyx7m1-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require')

def migrate():
    """Adiciona coluna last_year_viewed na tabela users"""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            # Verifica se a coluna já existe
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='users' AND column_name='last_year_viewed';
            """))
            
            if result.fetchone():
                print("✅ Coluna 'last_year_viewed' já existe!")
            else:
                # Adiciona a coluna
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN last_year_viewed INTEGER;
                """))
                conn.commit()
                print("✅ Coluna 'last_year_viewed' adicionada com sucesso!")
                print("📊 Sincronizando anos existentes do last_month_viewed...")
                
                # Sincroniza anos existentes (extrai YYYY de YYYY-MM)
                conn.execute(text("""
                    UPDATE users 
                    SET last_year_viewed = CAST(SPLIT_PART(last_month_viewed, '-', 1) AS INTEGER)
                    WHERE last_month_viewed IS NOT NULL;
                """))
                conn.commit()
                print("✅ Anos sincronizados!")
                
    except Exception as e:
        print(f"❌ Erro na migração: {e}")
    finally:
        engine.dispose()

if __name__ == '__main__':
    print("🔄 Iniciando migração do banco de dados...")
    migrate()
    print("✅ Migração concluída!")
