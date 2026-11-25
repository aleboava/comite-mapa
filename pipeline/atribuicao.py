"""Escolhe o grupo de cada pessoa nova, sem mexer em quem já tem grupo.

Regras, em ordem:
1. Exterior → o grupo do tipo "exterior".
2. Resposta inválida (sem estado) → fica sem grupo e vai para o relatório.
3. A cidade da pessoa já tem gente em algum grupo → entra nesse grupo. Se a cidade está
   em mais de um grupo (ex.: capital de São Paulo), entra no menor deles.
   Quem informou só o estado conta como morador da capital.
4. Cidade nova, estado já presente → grupos do mesmo estado e da mesma "zona":
   - SP e MG: região metropolitana da capital × resto do estado;
   - RJ: capital × resto do estado;
   - demais estados: o estado inteiro.
   Entre esses grupos, entra no de centro mais próximo da cidade (empate: o menor).
5. Estado sem nenhum grupo → grupo de centro mais próximo (aviso no relatório).
Grupos que passarem do limite de tamanho são apontados no relatório, mas ninguém é
mudado de grupo automaticamente.
"""
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

REF = Path(__file__).resolve().parent.parent / 'referencia'


def distancia_km(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


class Atribuidor:
    def __init__(self, normalizador, grupos, config, ref: Path = REF):
        self.N = normalizador
        self.grupos = grupos                      # {grupo: {'nome', 'tipo'}}
        self.cfg = config
        rm = json.loads((ref / 'regioes_metropolitanas.json').read_text(encoding='utf-8'))
        self.rm = {uf: set(v) for uf, v in rm.items()}
        self.exterior = next((g for g, v in grupos.items() if v['tipo'] == 'exterior'), None)
        self.membros = defaultdict(list)          # grupo -> [Local]

    def cidade_ref(self, loc):
        return loc.cidade or self.N.capital_de(loc.uf)

    def zona(self, loc):
        regra = self.cfg.get('zonas_especiais', {}).get(loc.uf)
        cid = self.cidade_ref(loc)
        if regra == 'regiao_metropolitana':
            return 'rm' if cid in self.rm.get(loc.uf, ()) else 'resto'
        if regra == 'capital':
            return 'capital' if cid == self.N.capital_de(loc.uf) else 'resto'
        return 'estado'

    def registrar(self, grupo, loc):
        if grupo:
            self.membros[grupo].append(loc)

    def centro(self, grupo):
        pts = [(l.lat, l.lon) for l in self.membros[grupo] if l.lat is not None and not l.exterior]
        if not pts:
            return None
        return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))

    def escolher(self, loc):
        """Devolve (grupo, motivo)."""
        if loc.exterior:
            return self.exterior, 'exterior'
        if not loc.valido:
            return '', 'sem_local'
        brasil = [g for g, v in self.grupos.items() if v['tipo'] != 'exterior']
        cid = self.cidade_ref(loc)
        # 3) mesma cidade
        # (só contam membros que informaram a cidade; quem deu só o estado não define onde fica a capital)
        com_cidade = [g for g in brasil if any(l.cidade == cid and l.uf == loc.uf
                                               for l in self.membros[g] if not l.exterior)]
        if com_cidade:
            return min(com_cidade, key=lambda g: (len(self.membros[g]), g)), 'mesma_cidade'
        # 4) mesmo estado e mesma zona
        z = self.zona(loc)
        mesma_uf = [g for g in brasil if any(l.uf == loc.uf for l in self.membros[g])]
        mesma_zona = [g for g in mesma_uf if any(l.uf == loc.uf and l.cidade and self.zona(l) == z for l in self.membros[g])]
        cands, motivo = (mesma_zona, 'mesma_zona') if mesma_zona else (mesma_uf, 'mesmo_estado')
        if not cands:
            cands, motivo = brasil, 'mais_proximo_sem_estado'
        if loc.lat is None:
            return min(cands, key=lambda g: (len(self.membros[g]), g)), motivo
        # o mais próximo; em empate (até 5 km de diferença), o menor grupo
        return min(cands, key=lambda g: (round(distancia_km((loc.lat, loc.lon), self.centro(g) or (0, 0)) / 5),
                                         len(self.membros[g]), g)), motivo

    def tamanhos(self):
        return Counter({g: len(v) for g, v in self.membros.items()})
