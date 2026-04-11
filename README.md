# 📋 Diário Oficial Monitor — Nova Iguaçu

Monitora diariamente o [Diário Oficial da Prefeitura de Nova Iguaçu](https://doweb.novaiguacu.rj.gov.br) e exibe automaticamente os candidatos **convocados e aprovados** em uma página web.

**Custo: R$ 0,00** — tudo roda no GitHub (Actions + Pages).

---

## Como funciona

```
Todo dia útil às 08h (BRT)
  └─> GitHub Actions baixa o PDF do Diário Oficial
  └─> Python extrai os candidatos convocados
  └─> Dados salvos como JSON no próprio repositório
  └─> Site GitHub Pages atualizado automaticamente
  └─> Email enviado se houver convocações
```

---

## Deploy em 5 passos

### 1. Criar o repositório

1. Acesse [github.com/new](https://github.com/new)
2. Nome: **diario-oficial-monitor**
3. Visibilidade: **Privado** (ou público — sua escolha)
4. Clique em **Create repository**

### 2. Enviar o código

```bash
git init
git add .
git commit -m "feat: initial commit — Diário Oficial Monitor"
git remote add origin https://github.com/SEU_USUARIO/diario-oficial-monitor.git
git push -u origin main
```

### 3. Configurar GitHub Pages

1. Vá em **Settings → Pages**
2. Source: **Deploy from a branch**
3. Branch: **gh-pages** / **/ (root)**
4. Clique em **Save**

O site ficará em: `https://SEU_USUARIO.github.io/diario-oficial-monitor/`

### 4. Configurar os Secrets (email)

Acesse **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Valor |
|--------|-------|
| `EMAIL_USERNAME` | seu-email@gmail.com |
| `EMAIL_PASSWORD` | Senha de App do Gmail (veja abaixo) |
| `EMAIL_TO` | email-destino@gmail.com |

> **Como gerar a Senha de App do Gmail:**
> 1. Acesse [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
> 2. Selecione **Outro (nome personalizado)** → "Diário Oficial Monitor"
> 3. Copie a senha gerada (16 caracteres) e cole em `EMAIL_PASSWORD`

### 5. Rodar manualmente o primeiro scrape

1. Vá em **Actions → Diário Oficial — Scrape Diário**
2. Clique em **Run workflow → Run workflow**
3. Aguarde ~2 minutos
4. Acesse seu site!

---

## Estrutura do projeto

```
diario-oficial-monitor/
├── .github/
│   └── workflows/
│       └── daily-scrape.yml    ← Automação (cron + email + deploy)
├── scraper/
│   ├── main.py                 ← Orquestrador do pipeline
│   ├── fetcher.py              ← Baixa o PDF do portal
│   ├── parser.py               ← Extrai texto do PDF
│   ├── extractor.py            ← Identifica os convocados
│   └── requirements.txt        ← Dependências Python
├── data/
│   ├── index.json              ← Índice de todas as edições
│   └── YYYY-MM-DD.json         ← Dados de cada dia
├── web/
│   ├── index.html              ← Página principal
│   ├── css/style.css           ← Estilos
│   └── js/app.js               ← Lógica do frontend
└── README.md
```

---

## Agendamento

O scraper roda automaticamente:
- **Segunda a Sábado às 08:00 BRT** (11:00 UTC)
- O Diário Oficial de Nova Iguaçu não é publicado aos domingos

Para alterar o horário, edite `.github/workflows/daily-scrape.yml`:
```yaml
- cron: "0 11 * * 1-6"   # 11:00 UTC = 08:00 BRT
```

---

## Tecnologias utilizadas

| Tecnologia | Uso | Custo |
|-----------|-----|-------|
| GitHub Actions | Agendamento e automação | Gratuito |
| GitHub Pages | Hospedagem do site | Gratuito |
| Python 3.12 | Scraping e extração | Gratuito |
| pdfplumber | Leitura de PDFs | Gratuito |
| httpx | HTTP requests | Gratuito |
| BeautifulSoup4 | Parsing HTML | Gratuito |
| Vanilla JS | Frontend sem framework | Gratuito |

---

## Limites gratuitos do GitHub Actions

- **2.000 minutos/mês** para repositórios privados
- Cada execução leva ~2 minutos → **~30 dias de uso contínuo** dentro do limite
- Para repositórios **públicos**: minutos ilimitados

---

## Fonte dos dados

- Portal oficial: [doweb.novaiguacu.rj.gov.br](https://doweb.novaiguacu.rj.gov.br)
- Publicação: publicacao.semug@novaiguacu.rj.gov.br

> Este projeto não é oficial. Os dados são extraídos automaticamente e podem conter imprecisões.
> Sempre confirme as informações diretamente no Diário Oficial.
