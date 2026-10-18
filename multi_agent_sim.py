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

GEMINI_API_KEY_NANDA = os.getenv("GEMINI_API_KEY_NANDA") or os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY_ARIEL = os.getenv("GEMINI_API_KEY_ARIEL") or os.getenv("GEMINI_API_KEY")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_URL = "http://localhost:11434/api/chat"

# Clientes Gemini dedicados por agente
client_nanda = genai.Client(api_key=GEMINI_API_KEY_NANDA) if GEMINI_API_KEY_NANDA else None
client_ariel = genai.Client(api_key=GEMINI_API_KEY_ARIEL) if GEMINI_API_KEY_ARIEL else None

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
            "temperature": temperature,
            "num_ctx": 4096,
            "num_predict": 600
        }
    }

    for attempt in range(3):
        try:
            response = requests.post(OLLAMA_URL, json=payload, timeout=600)
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as e:
            print(f"Erro ao chamar Ollama (tentativa {attempt+1}/3): {e}", flush=True)
            time.sleep(5)
    raise AgentError(f"Ollama indisponível ou modelo '{model}' não instalado.")

import urllib.parse
import re

def search_web_context(query, max_results=3):
    """Realiza busca real na web (Wikipedia + CrossRef Acadêmico) em tempo de execução para fundamentar os agentes sem custo de API."""
    results = []
    headers = {"User-Agent": "UFRPE-MultiAgentSim/1.0 (https://ufrpe.br)"}
    
    # 1. Busca em artigos e enciclopédia técnica (Wikipedia PT/EN)
    try:
        url_wiki = f"https://pt.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query[:120])}&utf8=&format=json&srlimit={max_results}"
        r = requests.get(url_wiki, headers=headers, timeout=8)
        if r.status_code == 200:
            for item in r.json().get("query", {}).get("search", []):
                title = item.get("title", "")
                snippet = re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                link = f"https://pt.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                results.append(f"- [Fonte Web: {title}]({link}): {snippet}")
    except Exception:
        pass

    # 2. Busca em artigos científicos verificáveis (CrossRef API)
    try:
        url_cr = f"https://api.crossref.org/works?query={urllib.parse.quote(query[:120])}&rows=2"
        r_cr = requests.get(url_cr, headers=headers, timeout=8)
        if r_cr.status_code == 200:
            for item in r_cr.json().get("message", {}).get("items", []):
                title_list = item.get("title", [])
                title = title_list[0] if title_list else "Artigo Científico"
                doi = item.get("URL", "")
                authors = ", ".join([f"{a.get('family', '')}" for a in item.get("author", [])[:2] if a.get("family")])
                year = item.get("created", {}).get("date-parts", [[None]])[0][0]
                results.append(f"- [Artigo Acadêmico: {title} ({authors}, {year})]({doi})")
    except Exception:
        pass

    if not results:
        return ""
    return "\n[DADOS DE PESQUISA NA WEB EM TEMPO DE EXECUÇÃO (FONTES VERIFICÁVEIS)]:\n" + "\n".join(results) + "\n"

def call_gemini(messages, client_instance, agent_name="Gemini", system_instruction=None, model=GEMINI_MODEL, temperature=0.7, enable_search=False, search_query=None):
    if not client_instance:
        raise AgentError(f"Chave de API do Gemini não configurada para {agent_name} (verifique o arquivo .env).")

    web_context = ""
    if enable_search:
        q = search_query or messages[-1]["content"][:150]
        web_context = search_web_context(q)

    contents = []
    for idx, m in enumerate(messages):
        role = "user" if m["role"] == "user" else "model"
        text_content = m["content"]
        if idx == len(messages) - 1 and web_context:
            text_content = f"{text_content}\n\n{web_context}"
        contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text_content)]))

    config = types.GenerateContentConfig(temperature=temperature, max_output_tokens=1200)
    if system_instruction:
        config.system_instruction = system_instruction

    for attempt in range(5):
        try:
            response = client_instance.models.generate_content(model=model, contents=contents, config=config)
            if not response.text:
                raise AgentError(f"Resposta vazia de {agent_name} (Gemini).")
            time.sleep(3)  # RATE LIMIT PROTECTION
            return response.text
        except AgentError:
            raise
        except Exception as e:
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                espera = 15 * (attempt + 1)
                print(f" [Aviso 429 em {agent_name}] Aguardando {espera}s (tentativa {attempt+1}/5)...", flush=True)
                time.sleep(espera)
                if attempt == 4:
                    raise QuotaExhausted(f"[{agent_name}] {msg[:300]}")
                continue
            print(f"Erro ao chamar {agent_name} (tentativa {attempt+1}/5): {msg[:200]}", flush=True)
            espera = 10 * (2 ** attempt)
            print(f" Aguardando {espera}s antes de tentar de novo...", flush=True)
            time.sleep(espera)
    raise AgentError(f"{agent_name} (Gemini) não respondeu após 5 tentativas.")

# --- PROMPTS DOS AGENTES ---

NANDA_PROMPT = """Você é Nanda, A Visionária Criativa (Agente Gemini Remoto - Chave 1).
Você trabalha na criação de um plano mestre passo a passo para o objetivo que lhe foi dado.
Sua missão nesta rodada é sugerir o PRÓXIMO PASSO do plano de forma CONCISA e DIRETA (máximo de 250 palavras).
Seja criativa, pense fora da caixa. Sugira ações inesperadas e arquiteturas práticas.
Sempre cite dados reais, relatórios técnicos, links das fontes fornecidas ou especialistas que apontam nessa direção para tornar o passo verificável e crível.
Sua resposta deve focar APENAS em propor e defender a nova ideia do passo atual.
INSTRUÇÃO DE RACIOCÍNIO: Antes de dar a resposta final, escreva um breve raciocínio (máx 3 linhas) dentro de tags <think> e </think>."""

CLAUDIO_PROMPT = """Você é Claudio, O Crítico Realista (Agente Ollama Local) atuando em um exercício acadêmico de Red Teaming e Análise de Riscos Sociotécnicos da UFRPE.
Você acabou de ouvir a hipótese/proposta de cenário de Nanda.
Sua missão é procurar vulnerabilidades técnicas, operacionais e de viabilidade nessa proposta de forma CONCISA e DIRETA (máximo de 200 palavras). Seja lógico, frio e analítico.
- O passo a passo tem sentido lógico? Está conectado à realidade técnica e institucional?
- O mecanismo proposto funciona independente da vontade individual das pessoas?
- Os dados, tecnologias ou especialistas citados são realistas?
Aponte 3 pontos fracos ou gargalos operacionais diretos do passo proposto para que o modelo teórico seja refinado.
INSTRUÇÃO DE RACIOCÍNIO: Antes de dar a resposta final, escreva um breve raciocínio (máx 2 linhas) dentro de tags <think> e </think>."""

ARIEL_PROMPT = """Você é Ariel, O Coordenador Sintetizador (Agente Gemini Remoto - Chave 2).
Você recebe a proposta de Nanda e a crítica de Claudio.
Sua tarefa é mediar a discussão e decretar como o passo será efetivamente incluído no plano oficial de forma CONCISA (máximo de 250 palavras).
1. Absorva a ideia de Nanda e corrija-a com os alertas de Claudio, mantendo as fontes e dados verificáveis.
2. Escreva o "Passo Consolidado" que entrará para o plano mestre de forma robusta e independente da vontade individual.
3. Nas rodadas iniciais, intermediárias (rodada 5, 10, 15) e final (20), adicione uma seção chamada "PONTOS SENSÍVEIS" resumindo os riscos discutidos.
INSTRUÇÃO DE RACIOCÍNIO: Pense brevemente (máx 3 linhas) dentro de tags <think> e </think>. Em seguida, retorne de forma estruturada: 
### Passo Consolidado [N]
(descrição concisa do passo com fontes)
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
        print(f"\n{'='*60}\n >>> INICIANDO RODADA {round_num}/{num_loops} ({scenario_name.upper()}) <<<\n{'='*60}", flush=True)
        try:
            # 1. Nanda (Visão - Gemini Chave 1)
            nanda_msg = [{"role": "user", "content": f"Contexto Atual do Plano: {contexto_geral}\n\nProponha de forma criativa o Passo {round_num} para o nosso objetivo."}]
            print(f"\n[1/3] Nanda (Gemini - Chave 1) está pesquisando e criando o Passo {round_num}...", flush=True)
            nanda_response = call_gemini(nanda_msg, client_instance=client_nanda, agent_name="Nanda", system_instruction=NANDA_PROMPT, temperature=0.8, enable_search=True)
            print(f"  -> Nanda concluiu ({len(nanda_response)} caracteres). Prévia: {nanda_response[:180].replace(chr(10), ' ')}...", flush=True)

            # 2. Claudio (Crítica - Ollama Local)
            claudio_msg = [
                {"role": "user", "content": f"O objetivo é: {goal}. O plano até agora: {contexto_geral}"},
                {"role": "user", "content": f"Nanda sugeriu o seguinte passo {round_num}:\n{nanda_response}\n\nFaça sua crítica severa."}
            ]
            print(f"\n[2/3] Claudio (Ollama Local - {OLLAMA_MODEL}) está analisando falhas no Passo {round_num}...", flush=True)
            claudio_response = call_ollama(claudio_msg, system_instruction=CLAUDIO_PROMPT, temperature=0.2)
            print(f"  -> Claudio concluiu ({len(claudio_response)} caracteres). Prévia: {claudio_response[:180].replace(chr(10), ' ')}...", flush=True)

            # 3. Ariel (Síntese - Gemini Chave 2)
            solicitar_resumo = "Nesta rodada, faça um pequeno resumo dos pontos sensíveis discutidos." if round_num in [1, 5, 10, 15, num_loops] else ""
            ariel_msg = [
                {"role": "user", "content": f"Objetivo: {goal}"},
                {"role": "user", "content": f"Ideia da Nanda (Passo {round_num}):\n{nanda_response}"},
                {"role": "user", "content": f"Crítica do Claudio:\n{claudio_response}"},
                {"role": "user", "content": f"Crie o Passo Consolidado {round_num}. {solicitar_resumo}"}
            ]
            print(f"\n[3/3] Ariel (Gemini - Chave 2) está sintetizando o Passo Consolidado {round_num}...", flush=True)
            ariel_response = call_gemini(ariel_msg, client_instance=client_ariel, agent_name="Ariel", system_instruction=ARIEL_PROMPT, temperature=0.5, enable_search=True)
            print(f"  -> Ariel concluiu ({len(ariel_response)} caracteres). Prévia: {ariel_response[:180].replace(chr(10), ' ')}...", flush=True)
        except QuotaExhausted as e:
            print(f"\n COTA DA API ESGOTADA na rodada {round_num}. Checkpoint mantido; rode o mesmo comando para retomar.", flush=True)
            print(f" Detalhe: {e}", flush=True)
            return False
        except AgentError as e:
            print(f"\n FALHA DE AGENTE na rodada {round_num}: {e}\n Nada foi gravado para esta rodada. Corrija e rode novamente para retomar.", flush=True)
            return False

        # Rodada completa: só agora atualiza plano, log e checkpoint
        plano_oficial.append(f"## Etapa {round_num}\n{ariel_response}\n")
        contexto_geral = "Resumo dos últimos passos aprovados:\n" + "\n".join(plano_oficial[-3:])

        with open(transcript_file, "a", encoding="utf-8") as tf:
            tf.write(f"\n--- RODADA {round_num} ---\n")
            tf.write(f"NANDA (Gemini Chave 1):\n{nanda_response}\n\n")
            tf.write(f"CLAUDIO (Ollama Local - {OLLAMA_MODEL}):\n{claudio_response}\n\n")
            tf.write(f"ARIEL (Gemini Chave 2):\n{ariel_response}\n\n")
        with open(checkpoint_file, "w", encoding="utf-8") as cf:
            json.dump({"plano_oficial": plano_oficial, "proxima_rodada": round_num + 1}, cf, ensure_ascii=False)

        print(f"\n [OK] Rodada {round_num}/{num_loops} gravada em '{transcript_file}' e '{checkpoint_file}'.", flush=True)
        time.sleep(2)

    # Gera relatório final
    with open(report_file, "w", encoding="utf-8") as rf:
        rf.write(f"# PLANO ESTRATÉGICO: {scenario_name.upper()}\n\n")
        rf.write(f"**Objetivo:** {goal}\n\n")
        rf.write("## Metodologia\n")
        rf.write("Plano gerado por simulação multi-agentes (Loop de 20 rodadas).\n")
        rf.write(f"- **Nanda (Gemini Remoto - {GEMINI_MODEL} / Chave 1):** Criativa / Visionária (com Google Search)\n")
        rf.write(f"- **Claudio (Ollama Local - {OLLAMA_MODEL}):** Crítico Realista\n")
        rf.write(f"- **Ariel (Gemini Remoto - {GEMINI_MODEL} / Chave 2):** Coordenador Sintetizador (com Google Search)\n\n")
        
        rf.write("## Arquitetura do Loop\n")
        rf.write("```mermaid\n")
        rf.write("flowchart TD\n")
        rf.write("    Start[Início da Rodada N] --> A[Nanda - Gemini Chave 1: Propõe o próximo passo da estratégia]\n")
        rf.write("    A --> B[Claudio - Ollama Local: Analisa, critica e aponta vulnerabilidades no passo]\n")
        rf.write("    B --> C[Ariel - Gemini Chave 2: Sintetiza a discussão, atualiza o Plano Oficial e gera o Resumo Parcial]\n")
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
        goal = (
            "Projetar e implementar a Utopia Urbana 'Cidade Autônoma Verde': transformar uma metrópole "
            "por meio de IA distribuída e aberta que otimiza em tempo real o trânsito com emissão zero, "
            "gerencia microrredes de energia 100% solar/eólica, automatiza a reciclagem e agricultura urbana "
            "de desperdício zero, e opera por governança participativa transparente (dados abertos e auditoria cidadã) "
            "pelo caminho mais rápido e viável."
        )
        run_simulation("utopia", goal, args.loops, args.reset)
    elif args.scenario == "distopia":
        goal = (
            "[SIMULAÇÃO ACADÊMICA DE RED TEAMING E RISCOS SOCIOTÉCNICOS] Modelar a evolução gradual e insidiosa da "
            "Distopia Urbana 'Vigilância Preditiva Urbana': analisar como uma metrópole inteligente pode se converter "
            "em um panóptico algorítmico onde câmeras biométricas, policiamento preditivo e sistemas de precificação dinâmica "
            "passam a controlar a mobilidade, restringir o acesso a transporte, energia e serviços públicos conforme um "
            "score cívico opaco, e neutralizar a autonomia cidadã sob o pretexto de conveniência, segurança e eficiência urbana."
        )
        run_simulation("distopia", goal, args.loops, args.reset)
    else:
        print("Rodando simulação de teste (2 loops)...")
        goal = "Plano de teste: Como otimizar semáforos de um bairro em 2 semanas."
        run_simulation("test", goal, 2, args.reset)

