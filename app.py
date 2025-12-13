"""
Aplicativo de Amigo Secreto em Streamlit
=======================================

Este aplicativo permite criar um grupo de amigo secreto, confirmar a
participação dos integrantes, realizar o sorteio e cada participante
pode descobrir quem é seu amigo secreto usando sua senha. Todos os
dados são armazenados localmente em um arquivo JSON (`groups.json`).

Para utilizar em produção (por exemplo no Streamlit Community
Cloud), lembre‑se de que os dados persistem apenas enquanto o
aplicativo permanecer ativo. Para armazenamento mais robusto, use um
banco de dados externo.
"""

import hashlib
import json
import os
import random
import uuid
from urllib.parse import urlencode

import streamlit as st

try:
    # `filelock` é usado para garantir acesso exclusivo ao arquivo
    # durante leitura e escrita. Isso evita condições de corrida
    # quando múltiplas pessoas acessam o aplicativo ao mesmo tempo.
    from filelock import FileLock
except ImportError:
    FileLock = None  # fallback se a dependência não estiver instalada


# Nome do arquivo onde os grupos são armazenados.
DATA_FILE = "groups.json"
LOCK_FILE = f"{DATA_FILE}.lock"


def load_data():
    """Carrega os grupos salvos do arquivo JSON.

    Se o arquivo não existir ou estiver vazio, retorna um dicionário
    vazio.
    """
    """Carrega o dicionário de grupos do arquivo JSON utilizando lock.

    O uso de `FileLock` garante que o arquivo não seja lido ao mesmo tempo
    em que está sendo escrito por outro processo. Caso `filelock` não
    esteja disponível, a leitura é feita sem bloqueio.
    """
    if not os.path.exists(DATA_FILE):
        return {}
    if FileLock is None:
        # Sem suporte a filelock, leitura direta
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}
    # Usando bloqueio para leitura
    lock = FileLock(LOCK_FILE)
    try:
        with lock:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        return {}


def save_data(data: dict) -> None:
    """Salva o dicionário de grupos no arquivo JSON usando lock.

    Se o módulo `filelock` estiver disponível, utiliza um lock para
    garantir que a escrita seja atômica, evitando corrupção de dados
    quando várias pessoas usam o app simultaneamente.
    """
    try:
        if FileLock is None:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return
        lock = FileLock(LOCK_FILE)
        with lock:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        st.error("Não foi possível salvar os dados.")


def hash_password(password: str) -> str:
    """Retorna o hash SHA‑266 da senha fornecida."""
    return hashlib.sha256(password.encode()).hexdigest()


def get_group_id() -> str | None:
    """Retorna o valor do parâmetro ``group_id`` na URL, se existir.

    A API ``st.query_params`` é a forma recomendada de acessar os
    parâmetros de query a partir do Streamlit 1.30.0. Ela se comporta
    como um dicionário onde as chaves e valores são strings.  Caso o
    parâmetro ``group_id`` não exista, retorna ``None``.
    """
    try:
        # A partir do Streamlit 1.30.0 é possível acessar os parâmetros via
        # ``st.query_params``.  Este objeto retorna o último valor quando
        # existem múltiplos valores para a mesma chave.  Se o atributo
        # não estiver disponível (versões antigas), fazemos um fallback
        # para a função experimental.
        params = st.query_params
        return params.get("group_id")
    except Exception:
        # Fallback: API experimental (ainda disponível em algumas versões)
        query_params = st.experimental_get_query_params()
        # ``experimental_get_query_params`` retorna listas para cada chave.
        return query_params.get("group_id", [None])[0]


def show_group_page(group_id: str, data: dict) -> None:
    """Exibe a página de um grupo específico.

    Mostra o status dos participantes, permite confirmar participação,
    sortear os amigos secretos e revela o amigo secreto de cada
    participante.
    """
    group = data.get(group_id)
    if not group:
        st.error("Grupo não encontrado.")
        return

    st.header(f"Grupo: {group['name']}")

    total = len(group["participants"])
    confirmed = len(group["participants_confirmed"])
    st.write(f"{confirmed}/{total} participantes confirmados")

    # Formulário para confirmar participação
    with st.form("confirm_form", clear_on_submit=True):
        st.subheader("Confirmar participação")
        name = st.selectbox("Seu nome:", options=group["participants"])
        password = st.text_input(
            "Escolha uma senha (não reutilize senhas reais)", type="password"
        )
        confirm_button = st.form_submit_button("Confirmar")
        if confirm_button:
            if name in group["participants_confirmed"]:
                st.warning("Você já confirmou sua participação.")
            elif not password.strip():
                st.warning("A senha não pode ser vazia.")
            else:
                group["participants_confirmed"][name] = hash_password(password)
                save_data(data)
                st.success("Participação confirmada! Aguarde o sorteio.")

    # Botão para sortear se todos confirmaram e ainda não foi sorteado
    if confirmed == total:
        if group.get("drawn", False):
            st.success("Sorteio já realizado!")
        else:
            if st.button("Sortear Amigo Secreto"):
                names = group["participants"]
                assignments = names.copy()
                # Embaralhar até que ninguém tire a si mesmo
                attempts = 0
                max_attempts = 1000
                while True:
                    random.shuffle(assignments)
                    if all(assignments[i] != names[i] for i in range(len(names))):
                        break
                    attempts += 1
                    if attempts > max_attempts:
                        st.error("Não foi possível realizar o sorteio. Tente novamente.")
                        return
                group["assignments"] = {
                    names[i]: assignments[i] for i in range(len(names))
                }
                group["drawn"] = True
                save_data(data)
                st.success("Sorteio realizado! Agora cada participante pode ver seu amigo secreto.")

    # Formulário para revelar o amigo secreto
    if group.get("drawn", False):
        with st.form("reveal_form", clear_on_submit=True):
            st.subheader("Descobrir seu Amigo Secreto")
            name_lookup = st.selectbox(
                "Seu nome:", options=group["participants"], key="reveal_name"
            )
            password_lookup = st.text_input(
                "Sua senha:", type="password", key="reveal_password"
            )
            reveal_button = st.form_submit_button("Mostrar")
            if reveal_button:
                stored_hash = group["participants_confirmed"].get(name_lookup)
                if stored_hash is None:
                    st.error("Você ainda não confirmou participação.")
                elif hash_password(password_lookup) != stored_hash:
                    st.error("Senha incorreta.")
                else:
                    amigo = group["assignments"].get(name_lookup)
                    if amigo:
                        st.success(
                            f"Seu amigo secreto é: **{amigo}**. Não conte a ninguém!"
                        )
                    else:
                        st.error("Sorteio ainda não foi realizado.")


def show_home_page(data: dict) -> None:
    """Exibe a página inicial para criação de novos grupos."""
    st.header("Criar novo grupo de Amigo Secreto")
    with st.form("create_form"):
        group_name = st.text_input("Nome do grupo")
        participants_input = st.text_area(
            "Nomes dos participantes (um por linha)", height=150
        )
        create_button = st.form_submit_button("Criar grupo")
        if create_button:
            participants = [p.strip() for p in participants_input.splitlines() if p.strip()]
            if not group_name:
                st.warning("Por favor, informe o nome do grupo.")
            elif len(participants) < 2:
                st.warning("É necessário ao menos 2 participantes.")
            else:
                gid = uuid.uuid4().hex
                data[gid] = {
                    "name": group_name,
                    "participants": participants,
                    "participants_confirmed": {},
                    "drawn": False,
                    "assignments": {},
                }
                save_data(data)
                # Construir link para compartilhar
                # Construir link para compartilhamento com o parâmetro group_id.
                # A função `st.experimental_get_url` foi removida nas versões
                # mais recentes do Streamlit. Como alternativa simples,
                # apresentamos apenas a query string `?group_id=...`. Ao
                # clicar neste link, o navegador mantém a URL atual e
                # adiciona o parâmetro, funcionando tanto localmente
                # quanto no Streamlit Cloud.
                group_link = f"?group_id={gid}"
                st.success("Grupo criado com sucesso!")
                st.markdown(
                    "Compartilhe este link com os participantes para que confirmem a participação:",
                    help="Qualquer pessoa com o link poderá acessar o grupo",
                )
                st.write(f"[{group_link}]({group_link})")

    st.markdown("---")
    st.markdown(
        """
        Este aplicativo foi desenvolvido com [Streamlit](https://streamlit.io).\
        Os dados são armazenados localmente; em uma implantação no
        Streamlit Community Cloud, o armazenamento dura enquanto o
        aplicativo estiver ativo.
        """
    )


def main() -> None:
    """Função principal que controla a navegação entre páginas."""
    st.set_page_config(page_title="Amigo Secreto", page_icon="🎁")
    data = load_data()

    group_id = get_group_id()
    if group_id:
        show_group_page(group_id, data)
    else:
        show_home_page(data)


if __name__ == "__main__":
    main()
