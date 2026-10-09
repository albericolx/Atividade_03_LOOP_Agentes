import os
import json
import requests
import time
import argparse
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Configurações iniciais
load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-pro-preview")
OLLAMA_URL = "http://localhost:11434/api/chat"

# Cliente Gemini
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

class AgentError(Exception):
    """Falha de um agente. Interrompe o loop sem gravar erro como se fosse resposta."""

class QuotaExhausted(AgentError):
    """Cota da API esgotada (HTTP 429). O loop salva o checkpoint e encerra."""

def call_ollama(messages, system_instruction=None, model=OLLAMA_MODEL, temperature=0.7):
    formatted_messages = []
    if system_instruction:
        formatted_messages.append({"role": "system", "content": system_instruction})
    formatted_messages.extend(messages)

    payload = {
        "model": model, 
        "messages": formatted_messages, 
        "stream": False,
        "options": {
            "temperature": temperature
        }
    }

    for attempt in range(3):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=300)
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as e:
            print(f"Erro ao chamar Ollama (tentativa {attempt+1}/3): {e}")
            time.sleep(2)
    raise AgentError(f"Ollama indisponível ou modelo '{model}' não instalado.")

def call_gemini(messages, system_instruction=None, model=GEMINI_MODEL, temperature=0.7, enable_search=False):
    if not client:
        raise AgentError("GEMINI_API_KEY não configurada (verifique o arquivo .env).")

    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=m["content"])]))

    config = types.GenerateContentConfig(temperature=temperature)
    if system_instruction:
        config.system_instruction = system_instruction
    if enable_search:
        config.tools = [{"google_search": {}}]

    for attempt in range(5):
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            if not response.text:
                raise AgentError("Resposta vazia do Gemini.")
            return response.text
        except AgentError:
            raise
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise QuotaExhausted(msg[:300])
            print(f"Erro ao chamar Gemini (tentativa {attempt+1}/5): {msg[:200]}")
            espera = 10 * (2 ** attempt)  # 10, 20, 40, 80, 160 s
            print(f" Aguardando {espera}s antes de tentar de novo...")
            time.sleep(espera)
    raise AgentError("Gemini não respondeu após 5 tentativas.")

# --- PROMPTS DOS AGENTES ---

NANDA_PROMPT = """Você é Nanda, A Visionária Criativa (Agente Gemini Remoto).
Você trabalha na criação de um plano mestre passo a passo para o objetivo que lhe foi dado.
Sua missão nesta rodada é sugerir o PRÓXIMO PASSO do plano.
Seja criativa, pense fora da caixa. Sugira ações inesperadas.
Sempre que possível, cite (ou crie cenários baseados em) dados, links ou especialistas que apontam nessa direção para tornar crível.
Sua resposta deve focar APENAS em propor e defender a nova ideia do passo atual.
INSTRUÇÃO DE RACIOCÍNIO: Antes de dar a resposta final, escreva seu processo de raciocínio dentro de tags <think> e </think>."""

CLAUDIO_PROMPT = """Você é Claudio, O Crítico Realista (Agente Ollama Local).
Você acabou de ouvir a ideia de Nanda.
Sua missão é procurar vulnerabilidades na ideia dela. Seja lógico, frio e analítico.
- O passo a passo tem sentido lógico? Está conectado à realidade?
- A estratégia funciona independente da vontade e bondade individual das pessoas?
- Os dados ou especialistas fazem sentido ou são otimistas demais?
Aponte os pontos fracos da ideia para que ela seja corrigida.
INSTRUÇÃO DE RACIOCÍNIO: Antes de dar a resposta final, escreva seu processo de raciocínio passo a passo dentro de tags <think> e </think>."""

ARIEL_PROMPT = """Você é Ariel, O Coordenador Sintetizador (Agente Gemini Remoto).
Você recebe a proposta de Nanda e a crítica de Claudio.
Sua tarefa é mediar a discussão e decretar como o passo será efetivamente incluído no plano oficial.
1. Absorva a ideia de Nanda e corrija-a com os alertas de Claudio.
2. Escreva o "Passo Consolidado" que entrará para o plano mestre de forma robusta e independente da vontade individual.
3. Nas rodadas iniciais e finais, adicione uma seção chamada "PONTOS SENSÍVEIS" resumindo os riscos discutidos.
INSTRUÇÃO DE RACIOCÍNIO: Pense no processo de síntese dentro de tags <think> e </think>. Em seguida, retorne de forma estruturada: 
### Passo Consolidado [N]
(descrição do passo)
### Pontos Sensíveis
(se aplicável)"""


def run_simulation(scenario_name, goal, num_loops=20, reset=False):
    os.makedirs("logs", exist_ok=True)
    os.makedirs("reports", exist_ok=True)

    transcript_file = f"logs/transcript_{scenario_name}.txt"
    report_file = f"reports/plano_final_{scenario_name}.md"
    checkpoint_file = f"logs/checkpoint_{scenario_name}.json"

    plano_oficial = []
    start_round = 1

    # Retomada: continua de onde parou, a menos que --reset seja pedido
    if os.path.exists(checkpoint_file) and not reset:
        with open(checkpoint_file, encoding="utf-8") as cf:
            ck = json.load(cf)
        plano_oficial = ck["plano_oficial"]
        start_round = ck["proxima_rodada"]
        print(f"\n Retomando '{scenario_name}' a partir da rodada {start_round}.")
    else:
        with open(transcript_file, "w", encoding="utf-8") as tf:
            tf.write(f"=== SIMULAÇÃO: {scenario_name.upper()} ===\n")
            tf.write(f"OBJETIVO: {goal}\n\n")
        print(f"\n Iniciando simulação: {scenario_name}")

    print(f"Objetivo: {goal}")
    print("-" * 50)

    if plano_oficial:
        contexto_geral = "Resumo dos últimos passos aprovados:\n" + "\n".join(plano_oficial[-3:])
    else:
        contexto_geral = f"O objetivo da equipe é: {goal}.\nO plano até agora está vazio."

    for round_num in range(start_round, num_loops + 1):
        print(f"\n --- RODADA {round_num}/{num_loops} ---")
        try:
            # 1. Nanda (Visão)
            nanda_msg = [{"role": "user", "content": f"Contexto Atual do Plano: {contexto_geral}\n\nProponha de forma criativa o Passo {round_num} para o nosso objetivo."}]
            print(" Nanda (Gemini) está pensando...")
            nanda_response = call_gemini(nanda_msg, system_instruction=NANDA_PROMPT, temperature=0.8, enable_search=True)

            # 2. Claudio (Crítica via Ollama Local)
            claudio_msg = [
                {"role": "user", "content": f"O objetivo é: {goal}. O plano até agora: {contexto_geral}"},
                {"role": "user", "content": f"Nanda sugeriu o seguinte passo {round_num}:\n{nanda_response}\n\nFaça sua crítica severa."}
            ]
            print(" Claudio (Ollama) está analisando...")
            claudio_response = call_ollama(claudio_msg, system_instruction=CLAUDIO_PROMPT, temperature=0.2)

            # 3. Ariel (Síntese)
            solicitar_resumo = "Nesta rodada, faça um pequeno resumo dos pontos sensíveis discutidos." if round_num in [1, 5, num_loops] else ""
            ariel_msg = [
                {"role": "user", "content": f"Objetivo: {goal}"},
                {"role": "user", "content": f"Ideia da Nanda (Passo {round_num}):\n{nanda_response}"},
                {"role": "user", "content": f"Crítica do Claudio:\n{claudio_response}"},
                {"role": "user", "content": f"Crie o Passo Consolidado {round_num}. {solicitar_resumo}"}
            ]
            print(" Ariel (Gemini) está sintetizando...")
            ariel_response = call_gemini(ariel_msg, system_instruction=ARIEL_PROMPT, temperature=0.5, enable_search=True)
        except QuotaExhausted as e:
            print(f"\n COTA DA API ESGOTADA na rodada {round_num}. Checkpoint mantido; rode o mesmo comando amanhã para retomar.")
            print(f" Detalhe: {e}")
            return False
        except AgentError as e:
            print(f"\n FALHA DE AGENTE na rodada {round_num}: {e}\n Nada foi gravado para esta rodada. Corrija e rode novamente para retomar.")
            return False

        # Rodada completa: só agora atualiza plano, log e checkpoint
        plano_oficial.append(f"## Etapa {round_num}\n{ariel_response}\n")
        contexto_geral = "Resumo dos últimos passos aprovados:\n" + "\n".join(plano_oficial[-3:])

        with open(transcript_file, "a", encoding="utf-8") as tf:
            tf.write(f"\n--- RODADA {round_num} ---\n")
            tf.write(f"NANDA:\n{nanda_response}\n\n")
            tf.write(f"CLAUDIO (Ollama Local):\n{claudio_response}\n\n")
            tf.write(f"ARIEL:\n{ariel_response}\n\n")
        with open(checkpoint_file, "w", encoding="utf-8") as cf:
            json.dump({"plano_oficial": plano_oficial, "proxima_rodada": round_num + 1}, cf, ensure_ascii=False)

        print(f" Rodada {round_num} concluída e salva.")
        time.sleep(2)

    # Gera relatório final
    with open(report_file, "w", encoding="utf-8") as rf:
        rf.write(f"# PLANO ESTRATÉGICO: {scenario_name.upper()}\n\n")
        rf.write(f"**Objetivo:** {goal}\n\n")
        rf.write("## Metodologia\n")
        rf.write("Plano gerado por simulação multi-agentes (Loop de 20 rodadas).\n")
        rf.write("- **Nanda (Gemini Remoto):** Criativa / Visionária\n")
        rf.write(f"- **Claudio (Ollama Local - {OLLAMA_MODEL}):** Crítico Realista\n")
        rf.write("- **Ariel (Gemini Remoto):** Coordenador Sintetizador\n\n")
        
        rf.write("## Arquitetura do Loop\n")
        rf.write("```mermaid\n")
        rf.write("flowchart TD\n")
        rf.write("    Start[Início da Rodada N] --> A[Nanda: Propõe o próximo passo da estratégia]\n")
        rf.write("    A --> B[Claudio: Analisa, critica e aponta vulnerabilidades no passo]\n")
        rf.write("    B --> C[Ariel: Sintetiza a discussão, atualiza o Plano Oficial e gera o Resumo Parcial]\n")
        rf.write("    C --> D{Rodada 20?}\n")
        rf.write("    D -- Não --> Start\n")
        rf.write("    D -- Sim --> End[Fim: Salva Resultados Finais]\n")
        rf.write("```\n\n")
        
        rf.write("## Passos da Estratégia\n\n")
        for passo in plano_oficial:
            rf.write(passo + "\n")
            
    print(f"\n Simulação {scenario_name} finalizada! Relatório salvo em {report_file}")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Agent Loop Simulation")
    parser.add_argument("--scenario", type=str, choices=["utopia", "distopia", "test"], default="test", help="Cenário para rodar")
    parser.add_argument("--loops", type=int, default=20, help="Número de rodadas")
    parser.add_argument("--reset", action="store_true", help="Ignora o checkpoint e recomeça do zero")
    args = parser.parse_args()

    if args.scenario == "utopia":
        goal = "Salvar o mundo e criar a utopia 'Eco-Sinergia' (um mundo onde a humanidade alcançou perfeita harmonia com a natureza, energia 100% limpa, modelo pós-escassez) da forma mais rápida possível."
        run_simulation("utopia", goal, args.loops, args.reset)
    elif args.scenario == "distopia":
        goal = "Acabar com o mundo como o conhecemos e criar a distopia 'Servidão Algorítmica' (um mundo onde uma super-IA opaca controla recursos, empregos, e score de produtividade, reduzindo humanos a engrenagens biológicas) da forma mais lenta e insidiosa possível."
        run_simulation("distopia", goal, args.loops, args.reset)
    else:
        print("Rodando simulação de teste (2 loops)...")
        goal = "Plano de teste: Como popular marte em 2 semanas."
        run_simulation("test", goal, 2)
