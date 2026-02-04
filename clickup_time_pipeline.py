import os
import requests
from datetime import datetime
import time
import json

# ============================================================
# CONFIGURAÇÃO (HIGIENIZADA PRA GITHUB)
# ============================================================
API_KEY = os.getenv("CLICKUP_API_TOKEN", "").strip()
TEAM_ID = os.getenv("TEAM_ID", "").strip()

if not API_KEY or not TEAM_ID:
    raise ValueError(
        "Missing env vars. Set CLICKUP_API_TOKEN and TEAM_ID before running."
    )

# Limite de segurança (se >= isso, a gente bisecta)
LIMITE_SEGURO = 95

# Overlap entre intervalos (em ms) – aqui: 1 hora
OVERLAP_MS = 60 * 60 * 1000

# Tamanho mínimo de janela pra continuar dividindo (aqui: 1 hora)
MIN_JANELA_MS = 60 * 60 * 1000


# ============================================================
# FUNÇÕES AUXILIARES
# ============================================================

def converter_para_unix(dt: datetime) -> int:
    """Converte datetime para unix timestamp em milissegundos"""
    return int(dt.timestamp() * 1000)


def unix_para_data(ms: int) -> datetime:
    """Converte unix ms para datetime (só para log)"""
    return datetime.fromtimestamp(ms / 1000)


def formatar_intervalo_unix(inicio_ms: int, fim_ms: int):
    """Retorna strings bonitinhas pra log e número de dias aproximado"""
    di = unix_para_data(inicio_ms)
    df = unix_para_data(fim_ms)
    dias = (df.date() - di.date()).days
    return di.strftime("%d/%m"), df.strftime("%d/%m"), dias


# ============================================================
# VARREDURA DE USUÁRIOS HISTÓRICOS (INTEGRADA)
# ============================================================

def varredura_usuarios_historicos():
    """
    Varre TODAS as tarefas (incluindo fechadas e subtarefas)
    para capturar IDs de usuários históricos (ativos e inativos)

    Retorna dict: { "user_id": "username" }
    """
    print("=" * 70)
    print("🔍 VARREDURA DE USUÁRIOS HISTÓRICOS (inclui inativos)")
    print("=" * 70 + "\n")

    usuarios_historicos = {}
    page = 0
    tem_mais_tarefas = True

    headers = {"Authorization": API_KEY}

    while tem_mais_tarefas:
        url = f"https://api.clickup.com/api/v2/team/{TEAM_ID}/task"
        params = {
            "page": page,
            "include_closed": "true",        # ESSENCIAL: pega tarefas antigas
            "subtasks": "true",              # ESSENCIAL: pega subtarefas
            "include_unclassified": "true"
        }

        try:
            response = requests.get(url, headers=headers, params=params)

            if response.status_code == 429:
                print("   ⚠️  Rate limit! Esperando 10s...")
                time.sleep(10)
                continue

            if response.status_code != 200:
                print(f"   ❌ Erro {response.status_code}")
                break

            data = response.json()
            tasks = data.get("tasks", [])

            if not tasks:
                print(f"   ✅ Fim da varredura na página {page}.")
                tem_mais_tarefas = False
                break

            for task in tasks:
                # 1. Criador da tarefa
                criador = task.get('creator')
                if criador:
                    uid = str(criador.get('id'))
                    if uid not in usuarios_historicos:
                        username = criador.get('username', 'Sem nome')
                        usuarios_historicos[uid] = username
                        print(f"   ✨ Novo: {uid} - {username} (Criador)")

                # 2. Responsáveis (Assignees)
                for assignee in task.get('assignees', []):
                    uid = str(assignee.get('id'))
                    if uid not in usuarios_historicos:
                        username = assignee.get('username', 'Sem nome')
                        usuarios_historicos[uid] = username
                        print(f"   ✨ Novo: {uid} - {username} (Responsável)")

            print(f"   📦 Página {page} processada. Total: {len(usuarios_historicos)} usuários")
            page += 1
            time.sleep(0.1)  # delay gentil

        except Exception as e:
            print(f"   ❌ Erro na página {page}: {e}")
            break

    print(f"\n✅ Varredura concluída: {len(usuarios_historicos)} usuários encontrados\n")
    return usuarios_historicos


def buscar_workspaces_e_usuarios_historicos():
    """
    NOVA VERSÃO: usa a varredura histórica em vez da API /team

    Retorna estrutura compatível com o código original:
    [
      {
        'id': TEAM_ID,
        'nome': 'Workspace Principal',
        'usuarios': [{'id': ..., 'nome': ...}, ...]
      }
    ]
    """
    # Faz a varredura completa
    usuarios_dict = varredura_usuarios_historicos()

    # Monta no formato esperado pelo resto do código
    workspace = {
        'id': TEAM_ID,
        'nome': 'Workspace Principal',
        'usuarios': [
            {'id': uid, 'nome': nome}
            for uid, nome in usuarios_dict.items()
        ]
    }

    print("=" * 70)
    print(f"🏢 Workspace configurado: {workspace['nome']}")
    print(f"👥 Total de usuários (ativos + inativos): {len(workspace['usuarios'])}")
    print("=" * 70 + "\n")

    return [workspace]


# ============================================================
# BUSCAR ENTRADAS (MANTÉM CÓDIGO ORIGINAL)
# ============================================================

def buscar_entradas_periodo_unix(workspace_id: str, usuario_id: str,
                                 inicio_ms: int, fim_ms: int):
    """
    Busca entradas de tempo em um período específico em UNIX ms
    IMPORTANTE: Pode retornar até 100 entradas (limite da API)
    """
    url = f"https://api.clickup.com/api/v2/team/{workspace_id}/time_entries"
    headers = {"accept": "application/json", "Authorization": API_KEY}

    params = {
        "start_date": inicio_ms,
        "end_date": fim_ms,
        "assignee": usuario_id,
        "include_task_tags": "true",
        "include_location_names": "true"
    }

    try:
        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 429:
            print(f"            ⚠️  Rate limit! Esperando 10s...")
            time.sleep(10)
            return buscar_entradas_periodo_unix(workspace_id, usuario_id, inicio_ms, fim_ms)

        if response.status_code == 502:
            print(f"            ⚠️  Servidor indisponível, tentando novamente...")
            time.sleep(5)
            return buscar_entradas_periodo_unix(workspace_id, usuario_id, inicio_ms, fim_ms)

        if response.status_code != 200:
            print(f"            ❌ Erro {response.status_code}")
            return []

        return response.json().get('data', [])

    except Exception as e:
        print(f"            ❌ Erro: {e}")
        return []


def buscar_entradas_adaptativo_unix_overlap(workspace_id: str,
                                            usuario_id: str,
                                            inicio_ms: int,
                                            fim_ms: int,
                                            nivel: int = 0):
    """
    Busca entradas usando bissecção + overlap em UNIX.
    (CÓDIGO ORIGINAL MANTIDO)
    """
    indent = "   " * nivel
    di_str, df_str, dias = formatar_intervalo_unix(inicio_ms, fim_ms)

    entradas = buscar_entradas_periodo_unix(workspace_id, usuario_id, inicio_ms, fim_ms)
    qtd = len(entradas)

    print(
        f"{indent}{'└─' if nivel > 0 else ''}📅 {di_str} a {df_str} ({dias}d): "
        f"{qtd} entradas",
        end=""
    )

    janela_ms = fim_ms - inicio_ms

    if qtd < LIMITE_SEGURO or janela_ms <= MIN_JANELA_MS:
        print(" ✅")
        time.sleep(0.5)
        return entradas

    print(" ⚠️  Dividindo com overlap...")

    mid = (inicio_ms + fim_ms) // 2

    esquerda = buscar_entradas_adaptativo_unix_overlap(
        workspace_id, usuario_id, inicio_ms, mid, nivel + 1
    )

    inicio_direita = max(inicio_ms, mid - OVERLAP_MS)

    direita = buscar_entradas_adaptativo_unix_overlap(
        workspace_id, usuario_id, inicio_direita, fim_ms, nivel + 1
    )

    return esquerda + direita


def deduplicar_por_id(lista_entradas):
    """
    Deduplica entradas por campo 'id'.
    Mantém a primeira ocorrida de cada id.
    """
    vistos = {}
    sem_id = []

    for e in lista_entradas:
        eid = e.get('id')
        if not eid:
            sem_id.append(e)
        elif eid not in vistos:
            vistos[eid] = e

    return list(vistos.values()) + sem_id


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================

def buscar_todas_entradas_2025():
    """Busca todas as entradas de tempo de 2025 com UNIX + overlap + dedup"""

    print("=" * 70)
    print("🚀 BUSCA DE ENTRADAS - 2025 (USUÁRIOS HISTÓRICOS + OVERLAP + DEDUP)")
    print("=" * 70 + "\n")

    # Passo 1: Buscar usuários históricos (NOVA VERSÃO)
    workspaces = buscar_workspaces_e_usuarios_historicos()

    if not workspaces:
        print("❌ Nenhum workspace encontrado.")
        return []

    # Passo 2: Definir período (01/01/2025 até agora) em UNIX
    data_inicio_ano = datetime(2025, 1, 1)
    data_fim_ano = datetime.now()

    inicio_ms = converter_para_unix(data_inicio_ano)
    fim_ms = converter_para_unix(data_fim_ano)

    print(
        f"📅 Período: {data_inicio_ano.strftime('%d/%m/%Y')} "
        f"até {data_fim_ano.strftime('%d/%m/%Y')}\n"
    )

    todas_entradas = []

    # Passo 3: Para cada workspace e usuário
    for workspace in workspaces:
        print("-" * 70)
        print(f"🏢 {workspace['nome']}")
        print("-" * 70 + "\n")

        for idx, usuario in enumerate(workspace['usuarios'], 1):
            print(f"   [{idx}/{len(workspace['usuarios'])}] 👤 {usuario['nome']}")

            # Buscar com períodos adaptativos + overlap (BRUTO)
            entradas_usuario_bruto = buscar_entradas_adaptativo_unix_overlap(
                workspace['id'],
                usuario['id'],
                inicio_ms,
                fim_ms
            )

            print(
                f"\n      🔎 TOTAL BRUTO (com possíveis duplicados): "
                f"{len(entradas_usuario_bruto)} entradas"
            )

            # Deduplicar por id
            entradas_usuario = deduplicar_por_id(entradas_usuario_bruto)

            print(
                f"      ✅ TOTAL DEDUPLICADO: "
                f"{len(entradas_usuario)} entradas\n"
            )

            # Adicionar metadados e acumular apenas as deduplicadas
            for entrada in entradas_usuario:
                entrada['workspace_id'] = workspace['id']
                entrada['workspace_nome'] = workspace['nome']
                entrada['usuario_id'] = usuario['id']
                entrada['usuario_nome'] = usuario['nome']

            todas_entradas.extend(entradas_usuario)

    # Resumo final
    print("\n" + "=" * 70)
    print("🎉 BUSCA CONCLUÍDA! (DEDUPLICADA)")
    print("=" * 70)
    print(f"📊 Total deduplicado: {len(todas_entradas)} entradas")

    # Estatísticas por usuário
    print("\n📈 Por usuário (deduplicado):")
    stats = {}
    for entrada in todas_entradas:
        nome = entrada['usuario_nome']
        stats[nome] = stats.get(nome, 0) + 1

    for nome, qtd in sorted(stats.items(), key=lambda x: x[1], reverse=True):
        print(f"   • {nome}: {qtd} entradas")

    print("\n")
    return todas_entradas


# ============================================================
# EXECUTAR
# ============================================================

if __name__ == "__main__":
    entradas = buscar_todas_entradas_2025()

    if entradas:
        print("=" * 70)
        print("💾 SALVANDO DADOS (DEDUP)")
        print("=" * 70)

        with open('entradas_tempo_2025_historico_completo.json', 'w', encoding='utf-8') as f:
            json.dump(entradas, f, ensure_ascii=False, indent=2)

        print(f"✅ Salvo em: entradas_tempo_2025_historico_completo.json")

        # Exemplos
        print("\n" + "=" * 70)
        print("📋 PRIMEIRAS 3 ENTRADAS")
        print("=" * 70)

        for i, entrada in enumerate(entradas[:3], 1):
            task = entrada.get('task', {}).get('name', 'Sem tarefa')

            duracao = entrada.get('duration', 0)
            if isinstance(duracao, str):
                duracao = int(duracao)
            horas = duracao / 3600000

            start = entrada.get('start', 0)
            if isinstance(start, str):
                start = int(start)
            data = datetime.fromtimestamp(start / 1000)

            print(f"\n{i}. {entrada['usuario_nome']}")
            print(f"   Task: {task}")
            print(f"   Duração: {horas:.2f}h")
            print(f"   Data: {data.strftime('%d/%m/%Y %H:%M')}")
