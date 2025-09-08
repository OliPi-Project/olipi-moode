# Contributing to OliPi-Project

First off, thanks for taking the time to contribute!
We welcome contributions of all kinds: bug fixes, new features, documentation improvements, and more.

---

## How to contribute

### 1. Fork & clone the repository
- Fork the repository you want to contribute to (e.g., `olipi-moode` or `olipi-core`).
- Clone it locally:

```bash
git clone https://github.com/YOUR_USERNAME/REPO_NAME.git
cd REPO_NAME
```

### 2. Create a branch
Always work on a separate branch:

```bash
git checkout -b feature/my-new-feature
```

### 3. Make your changes
- Keep code clean and readable.
- Write comments in **English**.
- Follow the existing coding style.
- Test your changes on a Raspberry Pi if possible.

### 4. Commit your changes
Use clear commit messages (English, imperative mood):

```bash
git commit -m "Add feature: support for ST7735 1.8 screen"
```

### 5. Push and open a Pull Request (PR)

```bash
git push origin feature/my-new-feature
```

Then go to GitHub and open a Pull Request.

---

## Testing

Before submitting:
- Run the code and check for errors.
- Ensure it doesn’t break existing functionality.
- If you add new features, update the documentation or `README.md`.

---

## Documentation

- All **print()**, comments, and log messages → in **English**.  
- User-facing messages (`show_message()`, YAML translations, help files) → in **English + French**.  
- Update `docs/` or the repository README if needed.

---

## ⚖️ Code of Conduct

Be respectful and constructive.  
This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/).

---

## 🛠 Useful commands

Set up a development environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Run the installer locally (testing mode):

```bash
python3 install/setup.py --dry-run
```

---

## 🙌 Need help?

- Open an [issue](https://github.com/OliPi-Project/olipi-moode/issues) for bugs or feature requests.  
- Start a [discussion](https://github.com/OliPi-Project/olipi-moode/discussions) for ideas or questions.  

Thanks for helping improve **OliPi-Project** 
