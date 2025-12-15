# Aplicativo de Amigo Secreto
#
# Este aplicativo permite criar grupos de amigo secreto de forma
# simples e direta. As pessoas se inscrevem com seus nomes e uma
# senha curta (não reutilize senhas reais) e o sorteio pode ser
# realizado quando todos confirmarem ou pelo próprio criador do
# grupo, que possui uma senha de criador. Os dados são
# armazenados localmente em ``groups.json`` enquanto o aplicativo
# estiver em execução.  Em implementações na nuvem, como o
# Streamlit Community Cloud, o armazenamento persiste apenas enquanto
# a aplicação permanece ativa.

import hashlib
import importlib.util
import json
import os
import random
import uuid
from collections.abc import Mapping
from urllib.parse import urlparse

import streamlit as st

try:
    # `filelock` é usado para garantir acesso exclusivo ao arquivo
    # durante leitura e escrita. Isso evita condições de corrida
    # quando múltiplas pessoas acessam o aplicativo ao mesmo tempo.
    from filelock import FileLock
except ImportError:
    FileLock = None  # fallback se a dependência não estiver instalada


pyperclip_spec = importlib.util.find_spec("pyperclip")
if pyperclip_spec:
    import pyperclip
else:
    pyperclip = None

# Nome do arquivo onde os grupos são armazenados.
DATA_FILE = "groups.json"
LOCK_FILE = f"{DATA_FILE}.lock"

# URL pública padrão usada como fallback quando não conseguimos detectar
# o endereço base automaticamente (ex.: em implantações no Streamlit
# Cloud). Pode ser sobrescrita com as variáveis de ambiente
# ``PUBLIC_BASE_URL`` ou ``BASE_URL``.
DEFAULT_PUBLIC_BASE_URL = "https://amigo-miyazaki.streamlit.app/~/+"


def load_data():
    """Carrega os grupos salvos do arquivo JSON.

    Se o arquivo não existir ou estiver vazio, retorna um dicionário
    vazio.  Quando disponível, utiliza ``FileLock`` para garantir
    exclusividade de leitura enquanto outro processo escreve.
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

    Se o módulo ``filelock`` estiver disponível, utiliza um lock para
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
    """Retorna o hash SHA‑256 da senha fornecida."""
    return hashlib.sha256(password.encode()).hexdigest()


def generate_temp_password() -> str:
    """Gera uma senha curta e aleatória para recuperações."""
    return uuid.uuid4().hex[:8]


def resolve_base_url(request: object | None) -> str:
    """Obtém a URL base a partir do host atual ou do ``st.secrets``.

    Primeiro tenta usar ``st.secrets['BASE_URL']`` para ambientes onde o
    endereço já é conhecido. Se não estiver definido, faz uma detecção a
    partir de ``st.request`` (quando disponível), considerando cabeçalhos
    comuns em proxies. Caso não seja possível determinar, utiliza um
    endereço público padrão configurável para garantir que o link gerado
    seja completo.
    """

    secret_base = (
        st.secrets.get("BASE_URL")
        if hasattr(st, "secrets") and isinstance(st.secrets, Mapping)
        else None
    )
    env_base = os.getenv("PUBLIC_BASE_URL") or os.getenv("BASE_URL")
    if isinstance(secret_base, str) and secret_base.strip():
        return secret_base.rstrip("/")
    if env_base and env_base.strip():
        return env_base.rstrip("/")

    if request is not None:
        try:
            if hasattr(request, "base_url") and request.base_url:
                return str(request.base_url).rstrip("/")

            headers = getattr(request, "headers", {}) or {}
            host = (
                headers.get("host")
                or headers.get("Host")
                or headers.get("x-forwarded-host")
                or headers.get("X-Forwarded-Host")
            )
            scheme = (
                headers.get("x-forwarded-proto")
                or headers.get("X-Forwarded-Proto")
                or headers.get("x-forwarded-scheme")
                or headers.get("X-Forwarded-Scheme")
                or "https"
            )

            if host:
                return f"{scheme}://{host}".rstrip("/")
        except Exception:
            return ""

    return DEFAULT_PUBLIC_BASE_URL.rstrip("/")


def build_full_group_link(group_id: str) -> str:
    """Monta a URL completa para compartilhar um grupo."""

    request = getattr(st, "request", None)
    base_url = resolve_base_url(request)

    path = ""
    if request is not None:
        try:
            if hasattr(request, "path"):
                path = request.path or ""
            elif hasattr(request, "url"):
                parsed_url = urlparse(str(request.url))
                path = parsed_url.path
        except Exception:
            path = ""

    parsed_base = urlparse(base_url)
    base_without_path = parsed_base._replace(path="", params="", query="", fragment="").geturl().rstrip("/")
    base_path = parsed_base.path or ""

    if not path and base_path:
        path = base_path
    elif not path:
        path = "/~/+"

    cleaned_path = f"/{(path.lstrip('/') if path else '').lstrip('/')}" if path else ""

    if base_without_path:
        return f"{base_without_path}{cleaned_path}?group_id={group_id}"

    return f"{cleaned_path or '?'}?group_id={group_id}" if cleaned_path else f"?group_id={group_id}"


def render_share_link(link: str, key_prefix: str) -> None:
    """Exibe o link e oferece um botão para copiar com instruções simples."""

    st.code(link, language="")
    button_key = f"copy_link_{key_prefix}"
    hint_key = f"copy_hint_{key_prefix}"

    if pyperclip is not None:
        if st.button("Copiar link", key=button_key):
            try:
                pyperclip.copy(link)
                st.success("Link copiado para a área de transferência.")
            except Exception:
                st.info(
                    "Copie manualmente: toque e segure o link no celular ou use Ctrl+C no computador."
                )
    else:
        if st.button("Copiar link", key=button_key):
            st.session_state[hint_key] = True

        if st.session_state.get(hint_key):
            st.write(
                "No celular, toque e segure o link acima para copiar. No computador, use Ctrl+C."
            )


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

    A página do grupo mostra quem já confirmou participação, permite
    confirmar sua presença, sortear os amigos secretos e descobrir
    quem você tirou. Para manter a experiência simples para pessoas
    mais velhas, usamos textos diretos e instruções claras.
    """
    group = data.get(group_id)
    if not group:
        st.error("Grupo não encontrado.")
        return

    # Garante compatibilidade com grupos criados antes do recurso de senhas temporárias
    group.setdefault("pending_passwords", {})

    st.title(f"Grupo: {group['name']}")

    share_link = build_full_group_link(group_id)
    st.markdown("**Link do grupo para compartilhar:**")
    render_share_link(share_link, key_prefix=f"group_{group_id}")

    total = len(group["participants"])
    confirmed = len(group["participants_confirmed"])
    st.markdown(f"**{confirmed}/{total}** participantes já confirmaram")

    st.markdown("### Como participar")
    st.markdown(
        "Escolha seu nome, confirme com uma senha curta e aguarde o sorteio. Depois use a mesma senha para ver quem tirou."
    )

    st.subheader("Sua participação")
    name = st.selectbox("Seu nome", options=group["participants"], key=f"participant_{group_id}")
    confirmed_hash = group["participants_confirmed"].get(name)
    draw_done = group.get("drawn", False)

    if confirmed_hash is None:
        with st.form(f"confirm_flow_{group_id}", clear_on_submit=True):
            password = st.text_input(
                "Crie uma senha", type="password", placeholder="Senha curta só para este grupo"
            )
            confirm_button = st.form_submit_button("Confirmar")
            if confirm_button:
                if not password.strip():
                    st.warning("A senha não pode ser vazia.")
                elif name in group["pending_passwords"] and hash_password(password) != group["pending_passwords"][name]:
                    st.error("Use a nova senha enviada pelo anfitrião.")
                else:
                    group["participants_confirmed"][name] = hash_password(password)
                    group["pending_passwords"].pop(name, None)
                    save_data(data)
                    st.success("Participação confirmada. Aguarde o sorteio.")
    elif not draw_done:
        st.info("Você já confirmou. Aguarde o sorteio.")
    
    # Botão para sortear se todos confirmaram e ainda não foi sorteado
    if confirmed == total:
        if group.get("drawn", False):
            st.success("Sorteio já realizado!")
        else:
            if st.button("Sortear automaticamente", key=f"sortear_{group_id}"):
                names = group["participants"]
                if len(names) < 2:
                    st.error("É necessário ao menos 2 participantes para sortear.")
                else:
                    assignments = names.copy()
                    attempts = 0
                    max_attempts = 1000
                    while True:
                        random.shuffle(assignments)
                        if all(assignments[i] != names[i] for i in range(len(names))):
                            break
                        attempts += 1
                        if attempts > max_attempts:
                            st.error(
                                "Não foi possível realizar o sorteio. Tente novamente."
                            )
                            return
                    group["assignments"] = {
                        names[i]: assignments[i] for i in range(len(names))
                    }
                    group["drawn"] = True
                    save_data(data)
                    st.success(
                        "Sorteio realizado! Agora cada participante pode ver seu amigo secreto."
                    )

    if draw_done:
        with st.form(f"reveal_flow_{group_id}", clear_on_submit=True):
            st.subheader("Ver seu Amigo Secreto")
            password_lookup = st.text_input(
                "Sua senha", type="password", key=f"reveal_password_{group_id}"
            )
            reveal_button = st.form_submit_button("Mostrar")
            if reveal_button:
                stored_hash = group["participants_confirmed"].get(name)
                if stored_hash is None:
                    st.error("Você ainda não confirmou participação.")
                elif hash_password(password_lookup) != stored_hash:
                    st.error("Senha incorreta.")
                else:
                    amigo = group["assignments"].get(name)
                    if amigo:
                        st.success(f"Seu amigo secreto é: **{amigo}**.")
                    else:
                        st.error("Sorteio ainda não foi realizado.")


    # Painel do criador: permite sortear a qualquer momento e adicionar participantes
    st.markdown("---")
    admin_flags = st.session_state.setdefault("admin_mode", {})
    admin_active = admin_flags.get(group_id, False)
    with st.expander("Painel do criador", expanded=False):
        if not admin_active:
            st.markdown(
                "**Somente o criador do grupo** pode sortear antes de todos confirmarem ou adicionar pessoas. Informe a senha abaixo para acessar estas funções."
            )
            creator_pw_input = st.text_input(
                "Senha do criador", type="password", key=f"creator_pw_{group_id}"
            )
            if st.button("Entrar no modo administrador", key=f"creator_login_{group_id}"):
                if "creator_password_hash" not in group:
                    st.error("Este grupo não possui senha de criador.")
                elif not creator_pw_input:
                    st.warning("Digite a senha do criador para entrar.")
                elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                    st.error("Senha do criador incorreta.")
                else:
                    admin_flags[group_id] = True
                    st.session_state["admin_mode"] = admin_flags
                    st.success("Modo administrador ativado. As ações avançadas foram liberadas.")
                    st.rerun()

        else:
            st.markdown("**Modo administrador ativo.** Use as opções abaixo com cuidado.")
            if st.button("Sair do modo administrador", key=f"creator_logout_{group_id}"):
                admin_flags.pop(group_id, None)
                st.session_state["admin_mode"] = admin_flags
                st.success("Você saiu do modo administrador.")
                st.rerun()
    
            # Botão para sortear agora, independentemente de confirmações
            if st.button(
                "Sortear agora (criador)", key=f"creator_sort_{group_id}"
            ):
                if group.get("drawn", False):
                    st.warning("O sorteio já foi realizado.")
                elif len(group["participants"]) < 2:
                    st.error("É necessário ao menos 2 participantes para sortear.")
                else:
                    # realizar sorteio
                    names = group["participants"]
                    assignments = names.copy()
                    attempts = 0
                    max_attempts = 1000
                    while True:
                        random.shuffle(assignments)
                        if all(assignments[i] != names[i] for i in range(len(names))):
                            break
                        attempts += 1
                        if attempts > max_attempts:
                            st.error(
                                "Não foi possível realizar o sorteio. Tente novamente."
                            )
                            return
                    group["assignments"] = {
                        names[i]: assignments[i] for i in range(len(names))
                    }
                    group["drawn"] = True
                    save_data(data)
                    st.success(
                        "Sorteio realizado! Agora cada participante pode ver seu amigo secreto."
                    )
    
            st.markdown("---")
            st.subheader("Ajustes do grupo")
            st.caption(
                "Aqui você corrige nomes ou refaz o sorteio quando alguém erra a senha. As mensagens são simples para evitar enganos."
            )
    
            new_group_name = st.text_input(
                "Editar nome do grupo",
                value=group["name"],
                key=f"rename_group_{group_id}",
                help="Use um nome fácil de reconhecer.",
            )
            if st.button("Salvar novo nome", key=f"save_group_name_{group_id}"):
                cleaned_group_name = new_group_name.strip()
                if not cleaned_group_name:
                    st.warning("O nome do grupo não pode ficar vazio.")
                else:
                    group["name"] = cleaned_group_name
                    save_data(data)
                    st.success("Nome do grupo atualizado com sucesso.")
    
            st.markdown("---")
            st.subheader("Ajustar confirmações")
            st.caption(
                "Use com cuidado. As ações abaixo pedem uma confirmação extra para evitar toques acidentais."
            )
    
            clear_container = st.container()
            with clear_container:
                participant_to_clear = st.selectbox(
                    "Quem precisa confirmar de novo?",
                    options=group["participants"],
                    key=f"clear_confirm_select_{group_id}",
                )
                confirm_clear = st.checkbox(
                    "Confirmar limpeza", key=f"confirm_clear_{group_id}"
                )
                if st.button(
                    "Limpar confirmação",
                    key=f"clear_confirm_btn_{group_id}",
                    use_container_width=True,
                ):
                    if not confirm_clear:
                        st.info("Marque a caixa para confirmar a limpeza.")
                    else:
                        group["participants_confirmed"].pop(participant_to_clear, None)
                        group["pending_passwords"].pop(participant_to_clear, None)
                        # Remove vínculos de sorteio para evitar confusão
                        group["assignments"].pop(participant_to_clear, None)
                        group["assignments"] = {
                            k: v for k, v in group["assignments"].items() if v != participant_to_clear
                        }
                        save_data(data)
                        st.success(
                            f"Confirmação apagada. {participant_to_clear} precisará confirmar novamente com uma nova senha."
                        )

            reset_container = st.container()
            with reset_container:
                reset_confirm = st.checkbox(
                    "Confirmar reset do sorteio", key=f"reset_draw_check_{group_id}"
                )
                if st.button(
                    "Resetar sorteio",
                    key=f"reset_draw_btn_{group_id}",
                    use_container_width=True,
                ):
                    if not reset_confirm:
                        st.info("Marque a caixa acima para confirmar o reset.")
                    else:
                        group["assignments"] = {}
                        group["drawn"] = False
                        save_data(data)
                        st.success(
                            "Sorteio apagado. Você pode confirmar ajustes e sortear novamente com calma."
                        )
    
            st.markdown("---")
            st.subheader("Adicionar participante")
            st.caption("Inclua novas pessoas apenas se ainda não houver sorteio concluído.")
    
            # Campo para adicionar novo participante
            new_participant = st.text_input(
                "Adicionar novo participante", key=f"new_participant_{group_id}"
            )
            if st.button(
                "Adicionar participante", key=f"add_participant_{group_id}"
            ):
                if group.get("drawn", False):
                    st.warning("Não é possível adicionar participantes após o sorteio.")
                else:
                    name_to_add = new_participant.strip()
                    if not name_to_add:
                        st.warning("Informe o nome do novo participante.")
                    elif name_to_add in group["participants"]:
                        st.warning("Este participante já está no grupo.")
                    else:
                        group["participants"].append(name_to_add)
                        save_data(data)
                        st.success(f"{name_to_add} adicionado ao grupo.")
    
            st.markdown("---")
            st.subheader("Segurança e senhas")
            st.caption(
                "Use estas opções para recuperar o acesso do criador ou gerar uma senha temporária para quem perdeu a própria senha."
            )
    
            creator_pw_container = st.container()
            with creator_pw_container:
                st.markdown("**Redefinir senha do criador**")
                new_creator_password = st.text_input(
                    "Nova senha do criador", type="password", key=f"new_creator_pw_{group_id}"
                )
                confirm_creator_password = st.text_input(
                    "Repita a nova senha", type="password", key=f"confirm_creator_pw_{group_id}"
                )
                if st.button(
                    "Salvar senha do criador",
                    key=f"update_creator_pw_{group_id}",
                    use_container_width=True,
                ):
                    if not new_creator_password.strip():
                        st.warning("A nova senha do criador não pode ser vazia.")
                    elif new_creator_password != confirm_creator_password:
                        st.warning("As novas senhas não conferem.")
                    else:
                        group["creator_password_hash"] = hash_password(new_creator_password)
                        save_data(data)
                        st.success(
                            "Senha do criador atualizada. Guarde a nova senha e compartilhe apenas com quem ajudará a administrar o grupo."
                        )

            temp_pw_container = st.container()
            with temp_pw_container:
                st.markdown("**Gerar senha temporária para participante**")
                participant_to_reset = st.selectbox(
                    "Escolha o participante", options=group["participants"], key=f"reset_select_{group_id}"
                )
                custom_temp_password = st.text_input(
                    "Senha temporária (opcional)",
                    key=f"custom_temp_{group_id}",
                    placeholder="Deixe em branco para gerar automaticamente",
                )
                confirm_temp_reset = st.checkbox(
                    "Confirmar reinício", key=f"confirm_temp_reset_{group_id}"
                )
                if st.button(
                    "Reiniciar acesso",
                    key=f"reset_pw_{group_id}",
                    use_container_width=True,
                ):
                    if not confirm_temp_reset:
                        st.info("Marque a confirmação para reiniciar o acesso.")
                    else:
                        temp_password = custom_temp_password.strip() or generate_temp_password()
                        group["participants_confirmed"].pop(participant_to_reset, None)
                        group["pending_passwords"][participant_to_reset] = hash_password(
                            temp_password
                        )
                        save_data(data)
                        st.success(
                            f"A confirmação de {participant_to_reset} foi reiniciada e a senha antiga foi invalidada."
                        )
                        st.info(
                            f"Copie e envie esta senha para {participant_to_reset}: **{temp_password}**. \n"
                            "Ela precisará usar essa senha para confirmar a participação novamente."
                        )
    
            st.markdown("---")
            st.subheader("Gerenciar participantes")
            st.caption(
                "Use esta área com cuidado. Renomear ou excluir alguém antes do sorteio atualiza imediatamente as listas do grupo."
            )
    
            rename_container = st.container()
            with rename_container:
                selected_to_rename = st.selectbox(
                    "Quem você quer renomear?",
                    options=group["participants"],
                    key=f"rename_select_{group_id}",
                )
                new_name = st.text_input(
                    "Novo nome",
                    key=f"rename_input_{group_id}",
                    placeholder="Digite o novo nome",
                )
                confirm_rename = st.checkbox(
                    "Confirmar mudança de nome", key=f"confirm_rename_{group_id}"
                )
                if st.button(
                    "Renomear",
                    key=f"rename_btn_{group_id}",
                    use_container_width=True,
                ):
                    if not confirm_rename:
                        st.info("Marque a confirmação para renomear.")
                    elif group.get("drawn", False):
                        st.warning("Não é possível renomear após o sorteio.")
                    else:
                        cleaned_name = new_name.strip()
                        if not cleaned_name:
                            st.warning("Informe o novo nome do participante.")
                        elif cleaned_name in group["participants"]:
                            st.warning("Já existe alguém com este nome no grupo.")
                        else:
                            idx = group["participants"].index(selected_to_rename)
                            group["participants"][idx] = cleaned_name
                            if selected_to_rename in group["participants_confirmed"]:
                                group["participants_confirmed"][cleaned_name] = group[
                                    "participants_confirmed"
                                ].pop(selected_to_rename)
                            if selected_to_rename in group["pending_passwords"]:
                                group["pending_passwords"][cleaned_name] = group[
                                    "pending_passwords"
                                ].pop(selected_to_rename)
                            if selected_to_rename in group["assignments"]:
                                group["assignments"][cleaned_name] = group[
                                    "assignments"
                                ].pop(selected_to_rename)
                            for key, value in list(group["assignments"].items()):
                                if value == selected_to_rename:
                                    group["assignments"][key] = cleaned_name
                            save_data(data)
                            st.success(
                                f"{selected_to_rename} agora se chama {cleaned_name}. Atualizamos as confirmações e o sorteio."
                            )

            remove_container = st.container()
            with remove_container:
                selected_to_remove = st.selectbox(
                    "Quem você quer excluir?",
                    options=group["participants"],
                    key=f"remove_select_{group_id}",
                )
                confirm_delete = st.checkbox(
                    "Confirmar exclusão", key=f"confirm_remove_{group_id}"
                )
                if st.button(
                    "Excluir participante",
                    key=f"remove_btn_{group_id}",
                    use_container_width=True,
                ):
                    if group.get("drawn", False):
                        st.warning("Não é possível excluir participantes após o sorteio.")
                    elif not confirm_delete:
                        st.info("Marque a caixa de confirmação para evitar exclusões acidentais.")
                    else:
                        group["participants"] = [
                            p for p in group["participants"] if p != selected_to_remove
                        ]
                        group["participants_confirmed"].pop(selected_to_remove, None)
                        group["pending_passwords"].pop(selected_to_remove, None)
                        group["assignments"].pop(selected_to_remove, None)
                        group["assignments"] = {
                            k: v
                            for k, v in group["assignments"].items()
                            if v != selected_to_remove
                        }
                        save_data(data)
                        st.success(
                            f"{selected_to_remove} foi removido do grupo. As listas de confirmação e sorteio foram atualizadas."
                        )

def show_home_page(data: dict) -> None:
    """Exibe a página inicial para criação de novos grupos.

    A página inicial orienta o organizador a montar um grupo de amigo secreto
    em poucos passos. Utilizamos textos simples e uma lista de etapas
    para facilitar o preenchimento.
    """
    st.title("Organizar Amigo Secreto")
    st.markdown(
        """
        ### Como funciona?
        1. Informe o **nome do grupo** (por exemplo, "Natal 2025").
        2. Defina uma **senha do criador**. Somente quem possui essa senha
           poderá realizar o sorteio ou adicionar novas pessoas.
        3. Liste os participantes, colocando **um nome por linha**.
        4. Clique em **Criar grupo** e depois compartilhe o link gerado com seus amigos.
        """
    )
    with st.form("create_form"):
        group_name = st.text_input("Nome do grupo")
        creator_password_input = st.text_input(
            "Senha do criador", type="password", placeholder="Digite uma senha fácil de lembrar"
        )
        participants_input = st.text_area(
            "Nomes dos participantes (um por linha)", height=150,
            placeholder="Exemplo:\nAna\nBruno\nCarlos"
        )
        create_button = st.form_submit_button("Criar grupo")
        if create_button:
            normalized_participants: list[str] = []
            duplicate_names: set[str] = set()
            seen_normalized: set[str] = set()

            for raw_participant in participants_input.splitlines():
                cleaned = " ".join(raw_participant.split())
                if not cleaned:
                    continue

                normalized = cleaned.title()
                normalized_lower = normalized.lower()

                if normalized_lower in seen_normalized:
                    duplicate_names.add(normalized)
                    continue

                seen_normalized.add(normalized_lower)
                normalized_participants.append(normalized)

            if not group_name:
                st.warning("Por favor, informe o nome do grupo.")
            elif not creator_password_input.strip():
                st.warning("Por favor, defina uma senha para o criador.")
            elif duplicate_names:
                duplicates_list = ", ".join(sorted(duplicate_names))
                st.warning(
                    "Nomes duplicados encontrados (ignora maiúsculas/minúsculas): "
                    f"{duplicates_list}. Ajuste a lista antes de criar o grupo."
                )
            elif len(normalized_participants) < 2:
                st.warning("É necessário ao menos 2 participantes válidos.")
            else:
                gid = uuid.uuid4().hex
                data[gid] = {
                    "name": group_name,
                    "creator_password_hash": hash_password(creator_password_input),
                    "participants": normalized_participants,
                    "participants_confirmed": {},
                    "pending_passwords": {},
                    "drawn": False,
                    "assignments": {},
                }
                save_data(data)
                group_link = build_full_group_link(gid)
                st.success("Grupo criado com sucesso!")
                st.markdown(
                    "**Compartilhe este link com os participantes para que confirmem a participação:**"
                )
                render_share_link(group_link, key_prefix=gid)

    st.markdown("---")
    st.caption(
        "Este aplicativo usa dados locais enquanto estiver aberto. Não reutilize suas senhas reais."
    )


def main() -> None:
    """Função principal que controla a navegação entre páginas.

    Configura o layout da página para centralizar o conteúdo e mantém a
    barra lateral recolhida por padrão para evitar distrações. Em
    seguida, decide qual página mostrar com base no parâmetro
    ``group_id``.
    """
    st.set_page_config(
        page_title="Amigo Secreto",
        page_icon="🎁",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    data = load_data()

    group_id = get_group_id()
    if group_id:
        show_group_page(group_id, data)
    else:
        show_home_page(data)


if __name__ == "__main__":
    main()
