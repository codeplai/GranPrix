from pc_race.dominio.ranking import ResumenEquipo, calcular_ranking


def r(equipo, puntos=0, validas=4, tmedio=60.0, error=0.01):
    return ResumenEquipo(equipo, puntos, validas, tmedio, error)


def orden(ranking):
    return [p.resumen.equipo for p in ranking]


def posiciones(ranking):
    return [p.posicion for p in ranking]


def test_menos_intervenciones_gana_aunque_sea_mas_lento():
    ranking = calcular_ranking([r(1, puntos=2, tmedio=40), r(2, puntos=0, tmedio=90)])
    assert orden(ranking) == [2, 1]


def test_empate_en_intervenciones_gana_mas_vueltas_validas():
    ranking = calcular_ranking([r(1, validas=3), r(2, validas=4)])
    assert orden(ranking) == [2, 1]


def test_empate_en_vueltas_gana_menor_tiempo_medio():
    ranking = calcular_ranking([r(1, tmedio=70), r(2, tmedio=55)])
    assert orden(ranking) == [2, 1]


def test_empate_en_tiempo_gana_menor_error_de_pose():
    ranking = calcular_ranking([r(1, error=0.030), r(2, error=0.012)])
    assert orden(ranking) == [2, 1]


def test_empate_total_comparte_posicion_y_salta_la_siguiente():
    ranking = calcular_ranking([r(3), r(1), r(2, puntos=5)])
    assert orden(ranking) == [1, 3, 2]  # entre iguales manda el número de equipo
    assert posiciones(ranking) == [1, 1, 3]


def test_con_menos_de_tres_vueltas_validas_no_es_elegible_y_va_al_final():
    ranking = calcular_ranking([r(1, puntos=0, validas=2), r(2, puntos=9, validas=3)])
    assert orden(ranking) == [2, 1]
    assert [p.elegible for p in ranking] == [True, False]
    assert posiciones(ranking) == [1, None]


def test_tres_vueltas_validas_es_el_minimo_elegible():
    assert calcular_ranking([r(1, validas=3)])[0].elegible


def test_sin_tiempo_o_error_pierde_el_desempate():
    ranking = calcular_ranking([r(1, tmedio=None), r(2, tmedio=300)])
    assert orden(ranking) == [2, 1]
    ranking = calcular_ranking([r(1, error=None), r(2, error=1.0)])
    assert orden(ranking) == [2, 1]


def test_ranking_vacio():
    assert calcular_ranking([]) == ()
