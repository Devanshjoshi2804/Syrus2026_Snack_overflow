# NovaByte Technologies — Setup Guides

## 1. Backend Intern (Node.js) Local Setup

### Install Node.js 20 via `nvm`

```bash
export NVM_DIR="$HOME/.nvm"
mkdir -p "$NVM_DIR"
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
source "$NVM_DIR/nvm.sh"
nvm install 20
node --version
```

Expected result: `node --version` returns `v20.x.x`.

### Install `pnpm` and basic global tools

```bash
npm install -g pnpm@8 typescript nodemon
pnpm --version
tsc --version
```

Expected result: `pnpm --version` returns `8.x.x`.

### Configure Git identity

```bash
git config --global user.name "Your Name"
git config --global user.email "your.name@novabyte.dev"
git config --global init.defaultBranch main
git config --global pull.rebase false
```

### Clone starter repository

```bash
git clone https://github.com/NovaByte-Technologies/connector-runtime-demo.git
cd connector-runtime-demo
pnpm install
```

### Run the local service

```bash
pnpm dev
pnpm test
```

---

## 2. Junior Backend (Python / FastAPI)

### Install Python 3.11 and Poetry

```bash
python3.11 --version
curl -sSL https://install.python-poetry.org | python3.11 -
poetry --version
```

### Clone and bootstrap

```bash
git clone https://github.com/NovaByte-Technologies/workflow-core-demo.git
cd workflow-core-demo
poetry install
poetry run pytest
```

---

## 3. Frontend (React / TypeScript)

### Install dependencies

```bash
git clone https://github.com/NovaByte-Technologies/flowengine-web-demo.git
cd flowengine-web-demo
pnpm install
pnpm dev
```

### Required VS Code extensions

- ESLint
- Prettier
- Tailwind CSS IntelliSense
- GitLens
- EditorConfig

---

## 4. Platform / DevOps

### Install required tools

```bash
brew install terraform kubectl helm
terraform version
kubectl version --client
helm version
```

### Infrastructure repository

```bash
git clone https://github.com/NovaByte-Technologies/infrastructure-demo.git
cd infrastructure-demo
terraform fmt -check
```

---

## 5. Common Verification Steps

- `node --version` should return `v20.x.x` for Node-based roles.
- `pnpm --version` should return `8.x.x`.
- `git config --global user.email` should be your NovaByte email.
- Docker Desktop should be running before any container-based task.
- VPN access should be verified by opening `https://internal.novabyte.dev/health`.

---

*Document ID: KB-004*
*Last Updated: March 2026*
*Owner: Developer Experience Team*
