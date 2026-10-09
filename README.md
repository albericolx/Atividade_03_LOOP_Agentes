# Atividade 03: Loop de Agentes (Utopia e Distopia)

Esta pasta contém a entrega completa da atividade prática com múltiplos agentes de IA interagindo em loop.

## Pontos de Verificação (Checklist de Entrega)

- [x] **Subrepositório Estruturado:** `CONTEXT.md` detalha o projeto isolado.
- [x] **Diagrama e Fluxo:** Arquivo `DOCUMENTO_ARQUITETURA.md` contém o diagrama e protocolo.
- [x] **Especificação de Prompts e Temperatura:** Agentes usam prompts com controle de temperatura (Nanda=0.8, Claudio=0.2, Ariel=0.5).
- [x] **Capacidade de Busca:** Nanda e Ariel usam a ferramenta `google_search` em tempo de execução.
- [x] **Capacidade de Raciocínio (Thinking):** Uso de instruções para *Chain-of-Thought* (`<think>...</think>`).

## Arquivos Entregues

1. **`multi_agent_sim.py`**: O código-fonte principal em Python. Ele implementa o loop com os 3 agentes solicitados:
   - **Nanda** (Gemini API, Temp 0.8, Web Search, Thinking): Perfil Criativa/Visionária.
   - **Claudio** (Ollama Local, Temp 0.2, Thinking): Perfil Crítico Realista.
   - **Ariel** (Gemini API, Temp 0.5, Web Search, Thinking): Perfil Coordenador/Sintetizador.
2. **`DOCUMENTO_ARQUITETURA.md`**: Diagramas detalhados de papéis e fluxo de dados.
3. **`exemplos/`**: Relatórios de saídas finais (utopia e distopia).
4. **`artigo/`**: Projeto do artigo em formato Springer LNCS.

## Execução

O script suporta retomada automática (checkpoint) para contornar limites de API.

```bash
# Executa a simulação da Utopia
python multi_agent_sim.py --scenario utopia

# Executa a simulação da Distopia
python multi_agent_sim.py --scenario distopia
```
