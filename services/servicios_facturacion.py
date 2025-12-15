def get_servicios_facturables_por_cliente(cur, cliente: str):
    sql = """
        SELECT
            consec,
            tipo,
            estado,
            num_informe,
            buque_contenedor,
            cliente,
            contacto,
            detalle,
            continente,
            pais,
            puerto,
            operacion,
            surveyor,
            honorarios,
            costo_operativo,
            fecha_inicio,
            hora_inicio,
            fecha_fin,
            hora_fin,
            demoras,
            duracion,
            factura
        FROM servicios
        WHERE
            LOWER(TRIM(cliente)) = LOWER(%s)
            AND UPPER(TRIM(estado)) = 'FINALIZADO'
            AND num_informe IS NOT NULL
            AND TRIM(num_informe) <> ''
            AND (
                factura IS NULL
                OR TRIM(factura) = ''
            )
        ORDER BY fecha_inicio NULLS LAST
    """
    cur.execute(sql, (cliente,))
    return cur.fetchall()
