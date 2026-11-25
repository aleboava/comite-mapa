"""Testes rápidos: python -m unittest discover tests"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'pipeline'))
from normalizacao import Normalizador, parece_dado_pessoal  # noqa: E402
from atribuicao import Atribuidor  # noqa: E402

N = Normalizador()


class Normalizacao(unittest.TestCase):
    def caso(self, texto, cidade, uf):
        l = N.normalizar(texto)
        self.assertEqual((l.cidade, l.uf), (cidade, uf), texto)

    def test_formatos_comuns(self):
        self.caso('São Paulo/SP', 'São Paulo', 'SP')
        self.caso('sao paulo, sp', 'São Paulo', 'SP')
        self.caso('Campinas SP', 'Campinas', 'SP')
        self.caso('Rio de Janeiro - RJ', 'Rio de Janeiro', 'RJ')
        self.caso('Belo Horizonte Minas Gerais', 'Belo Horizonte', 'MG')
        self.caso('BH/MG', 'Belo Horizonte', 'MG')
        self.caso('GuaíbaRS', 'Guaíba', 'RS')
        self.caso('SÃo Paulo', 'São Paulo', 'SP')

    def test_so_estado_e_capital(self):
        self.caso('RJ', '', 'RJ')
        self.caso('Sp/sp', 'São Paulo', 'SP')

    def test_exterior_e_invalidos(self):
        self.caso('Porto/Portugal', 'Porto', 'EX')
        self.caso('Hah', '', '')
        self.caso('', '', '')

    def test_dado_pessoal_nunca_vira_local(self):
        self.assertTrue(parece_dado_pessoal('alguem@exemplo.com'))
        self.assertTrue(parece_dado_pessoal('(11) 94724-3796'))
        self.assertFalse(N.normalizar('alguem@exemplo.com').valido)


class Atribuicao(unittest.TestCase):
    def setUp(self):
        grupos = {'G1': {'nome': 'Capital', 'tipo': 'brasil'}, 'G2': {'nome': 'Interior', 'tipo': 'brasil'},
                  'G3': {'nome': 'Capital 2', 'tipo': 'brasil'}, 'GX': {'nome': 'Exterior', 'tipo': 'exterior'}}
        cfg = {'zonas_especiais': {'SP': 'regiao_metropolitana'}}
        self.A = Atribuidor(N, grupos, cfg)
        for _ in range(3):
            self.A.registrar('G1', N.normalizar('São Paulo/SP'))
        self.A.registrar('G3', N.normalizar('São Paulo/SP'))
        self.A.registrar('G2', N.normalizar('Campinas/SP'))

    def test_mesma_cidade_vai_para_o_menor(self):
        self.assertEqual(self.A.escolher(N.normalizar('São Paulo'))[0], 'G3')

    def test_cidade_nova_vai_para_a_mesma_zona(self):
        self.assertEqual(self.A.escolher(N.normalizar('Guarulhos/SP'))[0], 'G3')   # Grande SP
        self.assertEqual(self.A.escolher(N.normalizar('Sorocaba/SP'))[0], 'G2')    # interior

    def test_exterior(self):
        self.assertEqual(self.A.escolher(N.normalizar('Lisboa'))[0], 'GX')


if __name__ == '__main__':
    unittest.main()
