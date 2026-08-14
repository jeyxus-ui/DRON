"""
Crea o actualiza usuarios de la API del dron.

Uso:
    python backend/create_user.py <username> <password> [--role admin|operator] [--change-password]

Ejemplos:
    python backend/create_user.py admin "MiClaveSegura2024!" --role admin
    python backend/create_user.py piloto "OtraClaveSegura1"          # rol operator
    python backend/create_user.py admin "NuevaClave1" --change-password
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    parser = argparse.ArgumentParser(description="Gestión de usuarios de la API del dron")
    parser.add_argument("username", help="Nombre de usuario")
    parser.add_argument("password", help="Contraseña (mínimo 8 caracteres)")
    parser.add_argument("--role", default="operator", choices=["admin", "operator", "viewer"],
                        help="Rol del usuario (default: operator)")
    parser.add_argument("--change-password", action="store_true",
                        help="Actualiza la contraseña de un usuario existente")
    args = parser.parse_args()

    from backend.api.auth import store

    try:
        if store.get_user(args.username) and not args.change_password:
            print(f"[ERROR] El usuario '{args.username}' ya existe. Usa --change-password para cambiar su contraseña.")
            return 1
        if args.change_password:
            updated = store.set_password(args.username, args.password)
            if not updated:
                print(f"[ERROR] El usuario '{args.username}' no existe.")
                return 1
            print(f"[OK] Contraseña actualizada para '{args.username}'")
        else:
            store.create_user(args.username, args.password, role=args.role)
            print(f"[OK] Usuario '{args.username}' creado (rol: {args.role})")
        return 0
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 1
    except Exception as e:
        print(f"[ERROR] {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
