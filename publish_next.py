"""
Publie UNE seule vignette (la prochaine dans l'ordre) sur Instagram
via l'API Graph, en lisant/mettant à jour un fichier d'état local
(state.json) pour savoir où on en est.

Conçu pour être appelé à répétition par un workflow GitHub Actions
programmé plusieurs fois par jour — chaque exécution publie 1 tuile.

Variables d'environnement attendues (fournies en secrets GitHub) :
  - IG_USER_ID       : l'ID du compte Instagram Business (the_fugu_guest_house)
  - IG_ACCESS_TOKEN  : le token System User (longue durée / permanent)
  - GITHUB_REPOSITORY : fourni automatiquement par GitHub Actions (owner/repo)
"""

import json
import os
import sys
import time
import random
import requests

GRAPH_API_VERSION = "v25.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

TOTAL_TILES = 1254
TILES_DIR = "tiles"          # dossier du repo contenant 1.jpg, 2.jpg, ...
STATE_FILE = "state.json"
BRANCH = "main"

# Jitter aléatoire en début de run pour ne pas publier pile à l'heure cron
# (0 à 15 minutes). Le repo étant public, le temps de job GitHub Actions
# est illimité, donc pas de souci de coût à attendre.
MAX_JITTER_SECONDS = 15 * 60


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"next_index": 1}
    with open(STATE_FILE, "r") as f:
        return json.load(f)


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_image_url(index: int) -> str:
    repo = os.environ["GITHUB_REPOSITORY"]  # ex: "tonpseudo/fresque-repo"
    return f"https://raw.githubusercontent.com/{repo}/{BRANCH}/{TILES_DIR}/{index}.jpg"


def create_media_container(ig_user_id: str, access_token: str, image_url: str, caption: str) -> str:
    resp = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def wait_until_ready(creation_id: str, access_token: str, timeout_seconds: int = 120):
    """Attend que le container soit prêt (FINISHED) avant de publier."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        resp = requests.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        resp.raise_for_status()
        status = resp.json().get("status_code")

        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"Le container {creation_id} est passé en erreur côté Instagram.")

        time.sleep(5)

    raise TimeoutError(f"Le container {creation_id} n'est pas prêt après {timeout_seconds}s.")


def publish_container(ig_user_id: str, access_token: str, creation_id: str) -> str:
    resp = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
        data={
            "creation_id": creation_id,
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def main():
    ig_user_id = os.environ["IG_USER_ID"]
    access_token = os.environ["IG_ACCESS_TOKEN"]

    state = load_state()
    index = state["next_index"]

    if index > TOTAL_TILES:
        print(f"Toutes les {TOTAL_TILES} vignettes ont déjà été publiées. Rien à faire.")
        return

    jitter = random.randint(0, MAX_JITTER_SECONDS)
    print(f"Attente de {jitter}s (jitter) avant publication de la vignette {index}/{TOTAL_TILES}...")
    time.sleep(jitter)

    image_url = get_image_url(index)
    caption = f"{index}/{TOTAL_TILES}"  # simple, ajustable si tu veux une légende différente

    print(f"Création du container pour {image_url} ...")
    creation_id = create_media_container(ig_user_id, access_token, image_url, caption)

    print("Attente que le container soit prêt...")
    wait_until_ready(creation_id, access_token)

    print("Publication...")
    media_id = publish_container(ig_user_id, access_token, creation_id)
    print(f"✓ Vignette {index}/{TOTAL_TILES} publiée avec succès (media id: {media_id}).")

    state["next_index"] = index + 1
    save_state(state)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"✗ Échec de la publication : {e}", file=sys.stderr)
        sys.exit(1)
