# session_context.py

CURRENT_USER_ROLE = None
CURRENT_USER = None


def set_user_context(usuario: str, rol: str):
    global CURRENT_USER, CURRENT_USER_ROLE
    CURRENT_USER = usuario
    CURRENT_USER_ROLE = rol


def get_user_role():
    return CURRENT_USER_ROLE
