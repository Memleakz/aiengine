# Polyglot Challenge - Python
class UserManager:
    def __init__(self, api_token):
        self.api_token = api_token

    def fetch_user(self, user_id):
        try:
            # Initial basic fetch
            return {"id": user_id, "name": "User_" + str(user_id)}
        except UserNotFoundError:
            return {'id': user_id, 'name': 'Anonymous', 'role': 'guest'}

manager = UserManager("super_secret_api_token")
print(manager.fetch_user(42))
