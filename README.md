# Atividade 03: Loop de Agentes (Utopia e Distopia)

Esta pasta contém a entrega completa da atividade prática com múltiplos agentes de IA interagindo em loop.

## Arquivos Entregues

1. **`multi_agent_sim.py`**: O código-fonte principal em Python. Ele implementa o loop de 20 rodadas com os 3 agentes solicitados:
   - **Nanda**: Agente Remota (Gemini API) com perfil Criativa/Visionária.
   - **Claudio**: Agente Local (Antigravity SDK / Ollama fallback) com perfil Crítico Realista.
   - **Ariel**: Agente Remoto (Gemini API) com perfil Coordenador/Sintetizador.
2. **`plano_final_utopia.md`**: Arquivo de saída final respondendo "Como salvar o mundo da forma mais rápida" (Cenário Eco-Sinergia). Contém:
   - Arquitetura e diagrama do loop
   - Resumo das rodadas sensíveis (1, 5 e 20)
   - Sequência de passos lógicos baseada nos embates dos agentes.
3. **`plano_final_distopia.md`**: Arquivo de saída final respondendo "Como acabar com o mundo da forma mais insidiosa" (Cenário Servidão Algorítmica). Contém a mesma estrutura adaptada para a premissa distópica.
4. **`logs/`**: Pasta contendo os arquivos `transcript_utopia.txt`, `transcript_distopia.txt` e `transcript_test.txt` com as transcrições das respostas brutas dos diálogos de cada rodada.
5. **`requirements.txt`**: Dependências utilizadas (google-genai, google-antigravity, requests, etc).

## Execução

O script interage tanto com a API remota do Gemini quanto com um Agente Local.
Para executá-lo:
```bash
# Executa a simulação da Utopia (20 rodadas)
python multi_agent_sim.py --scenario utopia --loops 20

# Executa a simulação da Distopia (20 rodadas)
python multi_agent_sim.py --scenario distopia --loops 20
```
