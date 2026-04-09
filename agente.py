#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

GEMINI_MODEL = "gemini-pro"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
SUPABASE_TABLE = "leads"
CACHE_FILE = "processed_ids.json"
BACKUP_FILE = "leads_backup.json"
LOG_FILE = "agente.log"
WEB_DIR = Path(__file__).resolve().parent / "web"

NICHO_KEYWORDS = [
    "site",
    "landing page",
    "página",
    "loja virtual",
    "e-commerce",
    "instagram",
    "tráfego",
    "anúncio",
    "ads",
    "meta ads",
    "google ads",
    "automação",
    "agente",
    "inteligência artificial",
    "ia",
    "chatbot",
    "marketing",
    "agência",
    "preço",
    "valor",
    "orçamento",
    "quanto custa",
    "serviço",
    "contrato",
    "pacote",
    "logo",
    "identidade visual",
    "n8n",
    "webhook",
    "saas",
    "sistema",
    "app",
    "aplicativo",
]

MENSAGENS_TESTE = [
    {
        "id": "test_001",
        "nome": "carlos_teste",
        "username_instagram": "carlos_teste",
        "mensagem": "Oi, quanto custa um site profissional?",
    },
    {
        "id": "test_002",
        "nome": "ana.silva.mkt",
        "username_instagram": "ana.silva.mkt",
        "mensagem": "Vocês fazem automação com n8n?",
    },
    {
        "id": "test_003",
        "nome": "joao123",
        "username_instagram": "joao123",
        "mensagem": "oi tudo bem?",
    },
    {
        "id": "test_004",
        "nome": "dra.fernanda.estetica",
        "username_instagram": "dra.fernanda.estetica",
        "mensagem": "Quero uma landing page pra minha clínica, tem como?",
    },
    {
        "id": "test_005",
        "nome": "ze_random99",
        "username_instagram": "ze_random99",
        "mensagem": "rs kkkk que meme",
    },
    {
        "id": "test_006",
        "nome": "pedroloja_oficial",
        "username_instagram": "pedroloja_oficial",
        "mensagem": "vocês gerenciam tráfego pago? qual o valor mensal?",
    },
    {
        "id": "test_007",
        "nome": "marianamodas",
        "username_instagram": "marianamodas",
        "mensagem": "Preciso de um chatbot pro meu WhatsApp, vocês fazem?",
    },
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def get_env_var(name: str, default: str = "", required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and not value:
        logger.error(f"Variável de ambiente obrigatória não configurada: {name}")
    return value


def load_cache() -> Set[str]:
    cache_path = Path(CACHE_FILE)
    if not cache_path.exists():
        return set()

    try:
        with cache_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data.get("ids", []))
    except Exception as e:
        logger.error(f"Erro ao carregar cache: {e}")
        return set()


def save_cache(ids: Set[str]) -> None:
    cache_path = Path(CACHE_FILE)
    data = {
        "ids": list(ids),
        "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
    }
    try:
        with cache_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro ao salvar cache: {e}")


def fetch_conversations(page_id: str, token: str) -> List[Dict[str, Any]]:
    conversations = []
    url = f"https://graph.facebook.com/v19.0/{page_id}/conversations"
    params = {
        "platform": "instagram",
        "fields": "participants,messages{message,from,created_time,id}",
        "access_token": token,
    }

    while url:
        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            conversations.extend(data.get("data", []))
            paging = data.get("paging", {})
            url = paging.get("next")
            params = {}
            if url:
                time.sleep(0.3)
        except Exception as e:
            logger.error(f"Erro ao buscar conversas: {e}")
            break

    return conversations


def extract_messages(conversations: List[Dict[str, Any]], page_id: str) -> List[Dict[str, Any]]:
    messages = []

    for convo in conversations:
        convo_messages = convo.get("messages", {}).get("data", [])
        for msg in convo_messages:
            sender = msg.get("from", {})
            sender_id = sender.get("id")
            if sender_id and sender_id != page_id:
                messages.append(
                    {
                        "id": msg.get("id"),
                        "nome": sender.get("name", ""),
                        "username_instagram": sender.get("username", sender_id),
                        "mensagem": msg.get("message", ""),
                        "created_time": msg.get("created_time"),
                    }
                )
    return messages


def pre_filter(text: str) -> bool:
    if not text:
        return False
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in NICHO_KEYWORDS)


def classify_with_gemini(text: str, retries: int = 2) -> Dict[str, Any]:
    if not text:
        return {
            "is_lead": False,
            "nicho": "",
            "confianca": 0.0,
            "resumo": "",
        }

    prompt_text = (
        "Classifique a mensagem como lead ou não. Retorne apenas JSON com campos: "
        "is_lead (boolean), nicho (string), confianca (float entre 0 e 1), resumo (string). "
        "Analise se a mensagem tem interesse em serviços de marketing digital, site, landing page, ecommerce, "
        "automação, chatbot, tráfego pago ou identidade visual."
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": f"{prompt_text}\nMensagem: {text}"
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 150,
        }
    }

    api_key = get_env_var("GOOGLE_API_KEY", required=True)
    if not api_key:
        return {
            "is_lead": False,
            "nicho": "",
            "confianca": 0.0,
            "resumo": "",
        }

    headers = {
        "Content-Type": "application/json",
    }

    url = f"{GEMINI_URL}/{GEMINI_MODEL}:generateContent?key={api_key}"

    attempt = 0
    while attempt <= retries:
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            text_output = ""
            if isinstance(result, dict) and "candidates" in result:
                candidate = result["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    text_output = candidate["content"]["parts"][0]["text"]
            parsed = json.loads(text_output)
            return {
                "is_lead": bool(parsed.get("is_lead", False)),
                "nicho": parsed.get("nicho", ""),
                "confianca": float(parsed.get("confianca", 0.0) or 0.0),
                "resumo": parsed.get("resumo", ""),
            }
        except Exception as e:
            logger.warning(f"Tentativa {attempt + 1} falhou ao classificar: {e}")
            attempt += 1
            time.sleep((2 ** attempt))

    return {
        "is_lead": False,
        "nicho": "",
        "confianca": 0.0,
        "resumo": "",
    }


def save_lead_supabase(lead: Dict[str, Any]) -> bool:
    supabase_url = get_env_var("SUPABASE_URL", required=True).rstrip("/")
    supabase_key = get_env_var("SUPABASE_KEY", required=True)
    if not supabase_url or not supabase_key:
        return False

    url = f"{supabase_url}/rest/v1/{SUPABASE_TABLE}"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        response = requests.post(url, headers=headers, json=lead, timeout=30)
        response.raise_for_status()
        logger.info(f"Lead salvo no Supabase: {lead.get('username_instagram', '')}")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar lead no Supabase: {e}")
        return False


def get_leads_supabase() -> List[Dict[str, Any]]:
    supabase_url = get_env_var("SUPABASE_URL", required=True).rstrip("/")
    supabase_key = get_env_var("SUPABASE_KEY", required=True)
    if not supabase_url or not supabase_key:
        return []

    url = f"{supabase_url}/rest/v1/{SUPABASE_TABLE}"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Erro ao buscar leads no Supabase: {e}")
        return []


def update_lead_supabase(lead_id: str, updates: Dict[str, Any]) -> bool:
    supabase_url = get_env_var("SUPABASE_URL", required=True).rstrip("/")
    supabase_key = get_env_var("SUPABASE_KEY", required=True)
    if not supabase_url or not supabase_key:
        return False

    url = f"{supabase_url}/rest/v1/{SUPABASE_TABLE}?id=eq.{lead_id}"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        response = requests.patch(url, headers=headers, json=updates, timeout=30)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Erro ao atualizar lead no Supabase: {e}")
        return False


def delete_lead_supabase(lead_id: str) -> bool:
    supabase_url = get_env_var("SUPABASE_URL", required=True).rstrip("/")
    supabase_key = get_env_var("SUPABASE_KEY", required=True)
    if not supabase_url or not supabase_key:
        return False

    url = f"{supabase_url}/rest/v1/{SUPABASE_TABLE}?id=eq.{lead_id}"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Prefer": "return=minimal",
    }
    try:
        response = requests.delete(url, headers=headers, timeout=30)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Erro ao deletar lead no Supabase: {e}")
        return False


def save_lead_backup(lead: Dict[str, Any]) -> None:
    backup_path = Path(BACKUP_FILE)
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if backup_path.exists():
        try:
            with backup_path.open("r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = []

    existing.append({"lead": lead, "backup_created_at": datetime.now(timezone.utc).isoformat() + "Z"})
    try:
        with backup_path.open("w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        logger.info(f"Lead salvo em backup local: {lead.get('username_instagram', '')}")
    except Exception as e:
        logger.error(f"Erro ao salvar backup de lead: {e}")


def parse_log_summary() -> Dict[str, Any]:
    summary = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "ignored": 0,
        "not_qualified": 0,
        "supabase_saved": 0,
        "backup_saved": 0,
        "errors": 0,
        "actions": set(),
    }
    log_path = Path(LOG_FILE)
    if not log_path.exists():
        return summary

    today_prefix = datetime.now().strftime("%Y-%m-%d")
    try:
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.startswith(today_prefix):
                    continue
                if "Mensagem ignorada" in line:
                    summary["ignored"] += 1
                    summary["actions"].add("mensagens ignoradas")
                elif "Não é lead ou confianca insuficiente" in line:
                    summary["not_qualified"] += 1
                    summary["actions"].add("mensagens não qualificadas")
                elif "Lead salvo no Supabase" in line:
                    summary["supabase_saved"] += 1
                    summary["actions"].add("leads enviados ao Supabase")
                elif "Lead salvo em backup local" in line:
                    summary["backup_saved"] += 1
                    summary["actions"].add("leads salvos em backup")
                elif "Erro" in line:
                    summary["errors"] += 1
                    summary["actions"].add("erros")
    except Exception as e:
        logger.error(f"Erro ao ler log de resumo: {e}")

    return summary


def format_status_report() -> str:
    summary = parse_log_summary()
    report_lines = [
        f"Resumo do dia ({summary['date']}):",
        f"- Leads salvos no Supabase: {summary['supabase_saved']}",
        f"- Leads salvos em backup local: {summary['backup_saved']}",
        f"- Mensagens ignoradas: {summary['ignored']}",
        f"- Mensagens não qualificadas: {summary['not_qualified']}",
        f"- Erros registrados: {summary['errors']}",
    ]
    if summary["actions"]:
        report_lines.append(f"- Ações detectadas: {', '.join(sorted(summary['actions']))}")
    else:
        report_lines.append("- Nenhuma ação registrada hoje ainda.")
    return "\n".join(report_lines)


def get_chat_response(message: str) -> str:
    content = message.lower().strip()
    if not content:
        return "Escreva uma pergunta sobre leads ou status."
    if "lead" in content or "leads" in content:
        return format_status_report()
    if "status" in content or "resumo" in content or "desenvolvimento" in content or "fez" in content:
        return format_status_report()
    return "Use 'status', 'leads' ou 'o que fez'."


def run_chat_mode() -> None:
    print("Modo interativo de status ativado. Pergunte 'status', 'leads', 'o que fez', ou 'sair'.")
    while True:
        try:
            message = input("Você: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        if message in {"sair", "exit", "quit"}:
            break
        print(get_chat_response(message))


def create_web_app() -> Flask:
    app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="/static")
    CORS(app)

    @app.route("/")
    def index() -> str:
        return send_from_directory(str(WEB_DIR), "index.html")

    @app.route("/api/status")
    def api_status() -> Any:
        summary = parse_log_summary()
        summary["actions"] = list(summary["actions"])
        return jsonify({"summary": summary, "report": format_status_report()})

    @app.route("/api/chat", methods=["POST"])
    def api_chat() -> Any:
        data = request.get_json(silent=True) or {}
        message = data.get("message", "")
        return jsonify({"response": get_chat_response(message)})

    @app.route("/api/leads")
    def api_leads() -> Any:
        leads = get_leads_supabase()
        return jsonify({"leads": leads})

    @app.route("/api/leads/<lead_id>", methods=["PATCH"])
    def api_update_lead(lead_id: str) -> Any:
        data = request.get_json(silent=True) or {}
        success = update_lead_supabase(lead_id, data)
        return jsonify({"success": success}), (200 if success else 500)

    @app.route("/api/leads/<lead_id>", methods=["DELETE"])
    def api_delete_lead(lead_id: str) -> Any:
        success = delete_lead_supabase(lead_id)
        return jsonify({"success": success}), (200 if success else 500)

    return app


def run_web_mode() -> None:
    if not WEB_DIR.exists():
        logger.error(f"Diretório de interface web não encontrado: {WEB_DIR}")
        return
    app = create_web_app()
    print("Abrindo interface web em http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000)


def sync_backup_to_supabase() -> None:
    backup_path = Path(BACKUP_FILE)
    if not backup_path.exists():
        return

    try:
        with backup_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Erro ao ler backup: {e}")
        return

    remaining = []
    for item in data:
        lead = item.get("lead")
        if not lead:
            continue
        if not save_lead_supabase(lead):
            remaining.append(item)

    try:
        with backup_path.open("w", encoding="utf-8") as f:
            json.dump(remaining, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro ao atualizar arquivo de backup: {e}")


def build_lead(message: Dict[str, Any], classification: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "nome": message.get("nome", ""),
        "username_instagram": message.get("username_instagram", ""),
        "mensagem": message.get("mensagem", ""),
        "nicho_detectado": classification.get("nicho", ""),
        "resumo_ia": classification.get("resumo", ""),
        "confianca_ia": classification.get("confianca", 0.0),
        "data_criacao": datetime.now(timezone.utc).isoformat() + "Z",
        "status": "novo",
        "origem": "instagram_dm",
    }


def run_test_mode() -> None:
    logger.info("Executando em modo de teste")
    for message in MENSAGENS_TESTE:
        text = message.get("mensagem", "")
        if not pre_filter(text):
            logger.info(f"Mensagem ignorada no teste: {text}")
            continue

        classification = classify_with_gemini(text)
        lead = build_lead(message, classification)
        if classification.get("confianca", 0.0) >= 0.5 and classification.get("is_lead"):
            if not save_lead_supabase(lead):
                save_lead_backup(lead)
        else:
            logger.info(f"Não é lead ou confianca insuficiente: {text}")


def run_cycle(model: str, temperature: float, max_tokens: int) -> None:
    sync_backup_to_supabase()

    page_id = get_env_var("INSTAGRAM_PAGE_ID", required=True)
    token = get_env_var("INSTAGRAM_ACCESS_TOKEN", required=True)
    if not page_id or not token:
        logger.error("Credenciais do Instagram não configuradas")
        return

    conversations = fetch_conversations(page_id, token)
    messages = extract_messages(conversations, page_id)
    processed_ids = load_cache()

    for message in messages:
        message_id = message.get("id")
        if not message_id or message_id in processed_ids:
            continue

        text = message.get("mensagem", "")
        if not pre_filter(text):
            processed_ids.add(message_id)
            continue

        classification = classify_with_gemini(text)
        lead = build_lead(message, classification)

        if classification.get("is_lead") and classification.get("confianca", 0.0) >= 0.5:
            if not save_lead_supabase(lead):
                save_lead_backup(lead)
        else:
            logger.info(f"Mensagem não qualificada como lead: {text}")

        processed_ids.add(message_id)
        time.sleep(0.5)

    save_cache(processed_ids)


def main() -> None:
    load_dotenv()
    print("========================================")
    print("MAX ARTE DIGITAL — AGENTE DE LEADS v2.0")
    print("========================================")

    parser = argparse.ArgumentParser(description="Agente de leads para Instagram DM e Supabase")
    parser.add_argument("--loop", action="store_true", help="Executa em loop contínuo")
    parser.add_argument("--interval", type=int, default=300, help="Intervalo em segundos entre cada ciclo")
    parser.add_argument("--test", action="store_true", help="Executa modo de teste com mensagens simuladas")
    parser.add_argument("--sync-backup", action="store_true", help="Sincroniza backup local com Supabase")
    parser.add_argument("--status", action="store_true", help="Exibe resumo do dia a partir dos logs")
    parser.add_argument("--chat", action="store_true", help="Abre modo interativo para perguntas de status")
    parser.add_argument("--web", action="store_true", help="Abre a interface web de status e chat")
    parser.add_argument("--model", type=str, default=GEMINI_MODEL, help="Modelo Gemini a utilizar")
    parser.add_argument("--temperature", type=float, default=0.1, help="Temperatura para a geração de IA")
    parser.add_argument("--max-tokens", type=int, default=150, help="Número máximo de tokens para a IA")
    args = parser.parse_args()

    if args.sync_backup:
        sync_backup_to_supabase()
        return

    if args.status:
        print(format_status_report())
        return

    if args.chat:
        run_chat_mode()
        return

    if args.web:
        run_web_mode()
        return

    if args.test:
        run_test_mode()
        return

    if args.loop:
        while True:
            run_cycle(args.model, args.temperature, args.max_tokens)
            time.sleep(args.interval)
    else:
        run_cycle(args.model, args.temperature, args.max_tokens)


if __name__ == "__main__":
    main()
