# backend_api/services/servicios_facturacion.py

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
            cliente = %s
            AND estado = 'Finalizado'
            AND num_informe IS NOT NULL
            AND TRIM(num_informe) <> ''
            AND COALESCE(TRIM(factura), '') = ''
        ORDER BY fecha_inicio NULLS LAST
    """
    cur.execute(sql, (cliente,))
    return cur.fetchall()
