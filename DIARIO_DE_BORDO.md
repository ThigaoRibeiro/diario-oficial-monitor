# 📋 Diário de Bordo & Monitoramento — Ester de Oliveira Lessa da Silva

Este documento centraliza as informações da candidata monitorada, as regras de verificação das convocações no Diário Oficial e o **histórico cronológico de checagens** realizadas pelos agentes de IA.

---

## 👤 Dados da Candidata Monitorada
- **Nome Completo Oficial:** **ESTER DE OLIVEIRA LESSA DA SILVA**
- **Variações / Termos de Busca:**
  - `ESTER DE OLIVEIRA LESSA DA SILVA`
  - `ESTER DE OLIVEIRA LESSA`
  - `ESTER OLIVEIRA LESSA`
  - `OLIVEIRA LESSA`
- **Órgão Monitorado:** Prefeitura Municipal de Nova Iguaçu (PMNI)
- **Portal Oficial:** [DOWEB Nova Iguaçu](https://doweb.novaiguacu.rj.gov.br)
- **Status Geral:** **Ainda não foi convocada** em nenhuma das edições publicadas do Diário Oficial.
  *(Nota importante: A convocação de 21/07/2026 na Edição nº 2337 pertencia a Ester dos Santos Prado Freire Paulo, uma homônima de primeiro nome, e NÃO à Ester de Oliveira Lessa da Silva).*

---

## 🤖 Protocolo Obrigatório para o Agente AI
Sempre que o usuário solicitar uma verificação ("verifique se a ester foi chamada", "tem novidades?", etc.):

1. **Sincronizar Repositório:**
   - Executar `git pull origin master` em `diario-oficial-monitor` para obter as edições processadas pelo GitHub Actions.
2. **Consultar o Portal Oficial:**
   - Checar se existem novas edições publicadas no DOWEB no mesmo dia (ex: 2ª edição, edição extra) ainda não comitadas pelo workflow agendado.
3. **Buscar Termos-Chave:**
   - Varrer o texto dos novos PDFs pelos termos: `ESTER DE OLIVEIRA LESSA DA SILVA`, `ESTER DE OLIVEIRA LESSA` e `OLIVEIRA LESSA`.
4. **Atualizar este Diário de Bordo:**
   - Registrar uma nova linha na tabela abaixo com data/hora, agente, status (Chamada? Sim/Não), última edição verificada e notas detalhadas.

---

## 📅 Histórico de Verificações

| Data / Hora | Agente / Modelo | Foi Chamada? | Última Edição Verificada | Resumo & Observações |
| :--- | :--- | :---: | :--- | :--- |
| **07/10/2026 14:10** | Gemini / Antigravity | ❌ **Não** | Edição nº 2406 (07/10/2026 - II Edição) | Atualização cadastral do nome correto para **Ester de Oliveira Lessa da Silva**. Varredura em todo o histórico de edições do repositório (abril/2026 até hoje, 07/10/2026, totalizando mais de 140 edições). **Nenhuma convocação ou menção localizada**. Descartada homônima de 21/07/2026 (Ester dos Santos Prado Freire Paulo). |

*(Novas consultas devem ser registradas adicionando uma nova linha ao final da tabela acima)*
