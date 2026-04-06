#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import requests
from dotenv import load_dotenv

GEMINI_MODEL = "gemini-pro"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta2"
SUPABASE_TABLE = "leads"
CACHE_FILE = "processed_ids.json"
BACKUP_FILE = "leads_backup.json"
LOG_FILE = "agente.log"

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
        "updated_at": datetime.utcnow().isoformat() + "Z",
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
        "model": GEMINI_MODEL,
        "prompt": {
            "text": f"{prompt_text}\nMensagem: {text}"
        },
        "temperature": 0.1,
        "maxOutputTokens": 150,
    }

    api_key = os.getenv("GOOGLE_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    attempt = 0
    while attempt <= retries:
        try:
            response = requests.post(f"{GEMINI_URL}:generate", headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()
            text_output = ""
            if isinstance(result, dict):
                text_output = result.get("candidates", [{}])[0].get("output", "")
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
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{SUPABASE_TABLE}"
    headers = {
        "apikey": os.getenv("SUPABASE_KEY", ""),
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY', '')}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        response = requests.post(url, headers=headers, json=lead, timeout=30)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar lead no Supabase: {e}")
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

    existing.append({"lead": lead, "backup_created_at": datetime.utcnow().isoformat() + "Z"})
    try:
        with backup_path.open("w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erro ao salvar backup de lead: {e}")


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
        "data_criacao": datetime.utcnow().isoformat() + "Z",
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

    page_id = os.getenv("INSTAGRAM_PAGE_ID", "")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
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
    parser.add_argument("--model", type=str, default=GEMINI_MODEL, help="Modelo Gemini a utilizar")
    parser.add_argument("--temperature", type=float, default=0.1, help="Temperatura para a geração de IA")
    parser.add_argument("--max-tokens", type=int, default=150, help="Número máximo de tokens para a IA")
    args = parser.parse_args()

    if args.sync_backup:
        sync_backup_to_supabase()
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
