class UserService:
    def __init__(self):
        self._users = {}
        self._next_user_id = 1

    def register(self, username: str, password: str) -> dict:
        """
        用户注册
        :param username: 用户名
        :param password: 密码
        :return: 包含用户ID的字典，如 {'user_id': 123}
        """
        if not self._validate_username(username):
            return None

        if not self._validate_password(password):
            return None

        if username in self._users:
            return None

        user_id = self._next_user_id
        self._users[username] = {
            'user_id': user_id,
            'password': password,
        }
        self._next_user_id += 1

        return {'user_id': user_id}

    def _validate_username(self, username: str) -> bool:
        """验证用户名格式"""
        return 3 <= len(username) <= 20 and username.isalnum()

    def _validate_password(self, password: str) -> bool:
        """验证密码格式"""
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        return has_upper and has_lower and has_digit
