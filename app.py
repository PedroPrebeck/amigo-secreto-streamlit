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
import json
import os
import random
import uuid

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

    total = len(group["participants"])
    confirmed = len(group["participants_confirmed"])
    st.markdown(f"**{confirmed}/{total}** participantes já confirmaram")

    # Orientações simples para os participantes
    st.markdown(
        """
        ### Como participar?
        1. Selecione seu nome na lista e defina uma senha simples (não utilize a mesma senha de outros serviços).
        2. Clique em **Confirmar**. Você verá uma mensagem avisando que sua participação foi registrada.
        3. Aguarde o sorteio. Após o sorteio, retorne a esta página para descobrir quem você tirou.
        """
    )

    # Formulário para confirmar participação
    with st.form("confirm_form", clear_on_submit=True):
        st.subheader("Confirmar participação")
        name = st.selectbox("Seu nome", options=group["participants"])
        password = st.text_input(
            "Defina uma senha", type="password", placeholder="Digite uma senha fácil de lembrar"
        )
        confirm_button = st.form_submit_button("Confirmar")
        if confirm_button:
            if name in group["participants_confirmed"]:
                st.warning("Você já confirmou sua participação.")
            elif not password.strip():
                st.warning("A senha não pode ser vazia.")
            elif name in group["pending_passwords"] and hash_password(password) != group["pending_passwords"][name]:
                st.error(
                    "Use a nova senha enviada pelo anfitrião para concluir a confirmação."
                )
            else:
                group["participants_confirmed"][name] = hash_password(password)
                group["pending_passwords"].pop(name, None)
                save_data(data)
                st.success("Participação confirmada! Aguarde o sorteio.")

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

    # Painel do criador: permite sortear a qualquer momento e adicionar participantes
    st.markdown("---")
    with st.expander("Painel do criador", expanded=False):
        st.markdown(
            "**Somente o criador do grupo** pode sortear antes de todos confirmarem ou adicionar pessoas. Informe a senha abaixo para acessar estas funções."
        )
        # Campo para senha do criador (não deve ser armazenado em estado)
        creator_pw_input = st.text_input(
            "Senha do criador", type="password", key=f"creator_pw_{group_id}"
        )

        # Botão para sortear agora, independentemente de confirmações
        if st.button(
            "Sortear agora (criador)", key=f"creator_sort_{group_id}"
        ):
            if not creator_pw_input:
                st.warning("Digite a senha do criador para sortear.")
            elif "creator_password_hash" not in group:
                st.error("Este grupo não possui senha de criador.")
            elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                st.error("Senha do criador incorreta.")
            elif group.get("drawn", False):
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
            help="Use um nome fácil de reconhecer."
        )
        if st.button("Salvar novo nome", key=f"save_group_name_{group_id}"):
            cleaned_group_name = new_group_name.strip()
            if not creator_pw_input:
                st.warning("Digite a senha do criador para alterar o nome.")
            elif "creator_password_hash" not in group:
                st.error("Este grupo não possui senha de criador.")
            elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                st.error("Senha do criador incorreta.")
            elif not cleaned_group_name:
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

        col_fix1, col_fix2 = st.columns(2)
        with col_fix1:
            participant_to_clear = st.selectbox(
                "Quem precisa confirmar de novo?",
                options=group["participants"],
                key=f"clear_confirm_select_{group_id}",
            )
            confirm_clear = st.checkbox(
                "Eu entendi que essa pessoa vai precisar refazer a confirmação.",
                key=f"confirm_clear_{group_id}",
            )
            if st.button("Limpar confirmação", key=f"clear_confirm_btn_{group_id}"):
                if not creator_pw_input:
                    st.warning("Digite a senha do criador para limpar a confirmação.")
                elif "creator_password_hash" not in group:
                    st.error("Este grupo não possui senha de criador.")
                elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                    st.error("Senha do criador incorreta.")
                elif not confirm_clear:
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

        with col_fix2:
            reset_confirm = st.checkbox(
                "Quero apagar o sorteio atual e começar de novo.",
                key=f"reset_draw_check_{group_id}",
            )
            if st.button("Resetar sorteio", key=f"reset_draw_btn_{group_id}"):
                if not creator_pw_input:
                    st.warning("Digite a senha do criador para resetar o sorteio.")
                elif "creator_password_hash" not in group:
                    st.error("Este grupo não possui senha de criador.")
                elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                    st.error("Senha do criador incorreta.")
                elif not reset_confirm:
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
            if not creator_pw_input:
                st.warning("Digite a senha do criador para adicionar participantes.")
            elif "creator_password_hash" not in group:
                st.error("Este grupo não possui senha de criador.")
            elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                st.error("Senha do criador incorreta.")
            elif group.get("drawn", False):
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

        sec_col1, sec_col2 = st.columns(2)
        with sec_col1:
            st.markdown("**Redefinir senha do criador**")
            new_creator_password = st.text_input(
                "Nova senha do criador", type="password", key=f"new_creator_pw_{group_id}"
            )
            confirm_creator_password = st.text_input(
                "Repita a nova senha", type="password", key=f"confirm_creator_pw_{group_id}"
            )
            if st.button("Atualizar senha do criador", key=f"update_creator_pw_{group_id}"):
                if not creator_pw_input:
                    st.warning("Digite a senha atual do criador para alterar.")
                elif "creator_password_hash" not in group:
                    st.error("Este grupo não possui senha de criador.")
                elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                    st.error("Senha do criador incorreta.")
                elif not new_creator_password.strip():
                    st.warning("A nova senha do criador não pode ser vazia.")
                elif new_creator_password != confirm_creator_password:
                    st.warning("As novas senhas não conferem.")
                else:
                    group["creator_password_hash"] = hash_password(new_creator_password)
                    save_data(data)
                    st.success(
                        "Senha do criador atualizada. Guarde a nova senha e compartilhe apenas com quem ajudará a administrar o grupo."
                    )

        with sec_col2:
            st.markdown("**Gerar senha temporária para participante**")
            participant_to_reset = st.selectbox(
                "Escolha o participante", options=group["participants"], key=f"reset_select_{group_id}"
            )
            custom_temp_password = st.text_input(
                "Senha temporária (opcional)",
                key=f"custom_temp_{group_id}",
                placeholder="Deixe em branco para gerar automaticamente",
            )
            if st.button("Reiniciar acesso do participante", key=f"reset_pw_{group_id}"):
                if not creator_pw_input:
                    st.warning("Digite a senha do criador para gerar a nova senha.")
                elif "creator_password_hash" not in group:
                    st.error("Este grupo não possui senha de criador.")
                elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                    st.error("Senha do criador incorreta.")
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

        col1, col2 = st.columns(2)
        with col1:
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
            if st.button("Renomear participante", key=f"rename_btn_{group_id}"):
                if not creator_pw_input:
                    st.warning("Digite a senha do criador para renomear.")
                elif "creator_password_hash" not in group:
                    st.error("Este grupo não possui senha de criador.")
                elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                    st.error("Senha do criador incorreta.")
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

        with col2:
            selected_to_remove = st.selectbox(
                "Quem você quer excluir?",
                options=group["participants"],
                key=f"remove_select_{group_id}",
            )
            confirm_delete = st.checkbox(
                "Estou ciente de que esta ação remove a pessoa do grupo",
                key=f"confirm_remove_{group_id}",
            )
            if st.button("Excluir participante", key=f"remove_btn_{group_id}"):
                if not creator_pw_input:
                    st.warning("Digite a senha do criador para excluir.")
                elif "creator_password_hash" not in group:
                    st.error("Este grupo não possui senha de criador.")
                elif hash_password(creator_pw_input) != group["creator_password_hash"]:
                    st.error("Senha do criador incorreta.")
                elif group.get("drawn", False):
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
            participants = [p.strip() for p in participants_input.splitlines() if p.strip()]
            if not group_name:
                st.warning("Por favor, informe o nome do grupo.")
            elif not creator_password_input.strip():
                st.warning("Por favor, defina uma senha para o criador.")
            elif len(participants) < 2:
                st.warning("É necessário ao menos 2 participantes.")
            else:
                gid = uuid.uuid4().hex
                data[gid] = {
                    "name": group_name,
                    "creator_password_hash": hash_password(creator_password_input),
                    "participants": participants,
                    "participants_confirmed": {},
                    "pending_passwords": {},
                    "drawn": False,
                    "assignments": {},
                }
                save_data(data)
                # Construir link para compartilhar: usamos apenas a query string
                # ?group_id=... para que o navegador mantenha a URL base.
                group_link = f"?group_id={gid}"
                st.success("Grupo criado com sucesso!")
                st.markdown(
                    "**Compartilhe este link com os participantes para que confirmem a participação:**"
                )
                st.write(f"[{group_link}]({group_link})")

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