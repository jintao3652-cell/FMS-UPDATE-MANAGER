import requests


BASE_URL = "http://main.cnrpg.top:5245"
USERNAME = "navdata"
PASSWORD = "123456"
FOLDER_PATH = "/导航数据"


def login_and_get_token() -> str:
    payload = {
        "username": USERNAME,
        "password": PASSWORD,
    }

    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=15,
    )

    print("Login HTTP Status:", response.status_code)
    print("Login Response:", response.text)
    response.raise_for_status()

    data = response.json()
    token = data.get("token")
    if not token:
        token = data.get("data", {}).get("token")
    if not token:
        raise ValueError("Login succeeded but no token was found in the response.")
    return token


def list_folder(token: str) -> None:
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }

    payload = {
        "path": FOLDER_PATH,
        "page": 1,
        "per_page": 500,
        "refresh": False,
    }

    response = requests.post(
        f"{BASE_URL}/api/fs/list",
        headers=headers,
        json=payload,
        timeout=30,
    )

    print("HTTP Status:", response.status_code)
    print("Response:", response.text)

    if response.status_code != 200:
        return

    data = response.json()
    if data.get("code") != 200:
        print("API 错误:", data.get("message"))
        return

    items = data.get("data", {}).get("content", [])
    print(f"\n文件夹 '{FOLDER_PATH}' 内有 {len(items)} 个项目：")

    for item in items:
        if item.get("is_dir"):
            print(f"[文件夹] {item.get('name')}   (修改时间: {item.get('modified')})")
        else:
            print(
                f"[文件] {item.get('name')}   "
                f"大小: {item.get('size')} 字节   "
                f"修改时间: {item.get('modified')}"
            )


def list_folder_path(token: str, folder_path: str) -> dict:
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }

    payload = {
        "path": folder_path,
        "page": 1,
        "per_page": 500,
        "refresh": False,
    }

    response = requests.post(
        f"{BASE_URL}/api/fs/list",
        headers=headers,
        json=payload,
        timeout=30,
    )

    print(f"\nListing path: {folder_path}")
    print("HTTP Status:", response.status_code)
    print("Response:", response.text)

    if response.status_code != 200:
        return {}

    return response.json()


def print_items(folder_path: str, items: list) -> None:
    print(f"\n文件夹 '{folder_path}' 内有 {len(items)} 个项目：")
    for item in items:
        if item.get("is_dir"):
            print(f"[文件夹] {item.get('name')}   (修改时间: {item.get('modified')})")
        else:
            print(
                f"[文件] {item.get('name')}   "
                f"大小: {item.get('size')} 字节   "
                f"修改时间: {item.get('modified')}"
            )


def main() -> None:
    token = login_and_get_token()
    data = list_folder_path(token, FOLDER_PATH)
    if data.get("code") == 200:
        print_items(FOLDER_PATH, data.get("data", {}).get("content", []))
        return

    print("API 错误:", data.get("message"))
    print("目标路径不存在，正在列出根目录 '/' 供你确认真实路径...")

    root_data = list_folder_path(token, "/")
    if root_data.get("code") == 200:
        print_items("/", root_data.get("data", {}).get("content", []))
    else:
        print("根目录读取失败:", root_data.get("message"))


if __name__ == "__main__":
    main()
