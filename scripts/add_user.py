import sys
import pathlib

# Add root and src to path
sys.path.insert(0, str(pathlib.Path('.').resolve()))
sys.path.insert(0, str(pathlib.Path('src').resolve()))

from backend.app.config import get_settings
from iris.store_registry import init_db, create_role, upsert_user_account

db = get_settings().db_path_obj
init_db(db)

# Ensure roles exist before assignment
try:
    create_role(db, 'admin', 'Root permission', 'ALL')
except TypeError:
    # Older signature fallback
    create_role(db, 'admin', 'ALL')
except Exception:
    pass

try:
    create_role(db, 'user', 'Basic viewer', 'READ_ONLY')
except TypeError:
    create_role(db, 'user', 'READ_ONLY')
except Exception:
    pass

upsert_user_account(db, 'vishal.nayak@kushals.com', 'ChangeMe123!', 'Vishal Nayak', 'BLRJAY', ['admin'])
print("Successfully generated user vishal.nayak@kushals.com")
