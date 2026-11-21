# Control de inscripciones — Olimpiadas Regionales

Aplicación web interna para recibir archivos de inscripción, normalizar los datos y señalar registros que necesitan revisión. Está pensada para reducir el trabajo manual provocado por encabezados, nombres y formatos inconsistentes.

## Funciones principales

- Carga CSV y XLSX sin convertir las identificaciones a números.
- Reconoce CSV con coma o punto y coma y codificaciones comunes de Windows.
- Normaliza nombres, colegios, departamentos, municipios, niveles, género y sector.
- Conserva `Grado` y lo mantiene separado de `Nivel`.
- Detecta campos faltantes, identificaciones no numéricas, longitudes inusuales y duplicados.
- Indica la fila del archivo original que debe revisarse.
- Permite filtrar y descargar los datos o solamente los problemas en CSV y Excel.
- Cruza un consolidado limpio con cuatro reportes de calificaciones por identificación.

> Los archivos de inscripción contienen datos personales. La carpeta `Data/` está excluida de Git y no debe publicarse ni compartirse sin autorización.

## Instalación en Windows

Se recomienda Python 3.10 o superior.

```powershell
cd C:\Users\madar\Olimpiadas_programa
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Las herramientas opcionales para desarrollo se instalan con:

```powershell
pip install -r requirements-extras.txt
```

## Ejecutar la aplicación

```powershell
streamlit run scripts/streamlit_dashboard.py
```

También puedes iniciarla con:

```powershell
python main.py
```

Streamlit mostrará una dirección local, normalmente `http://localhost:8501`.

## Formato recomendado

La aplicación intenta reconocer variantes de los encabezados. Para obtener el mejor resultado, usa estas columnas:

- `Numero identificacion`
- `Nombres`
- `Apellidos`
- `Nombre del colegio o institución educativa`
- `Departamento`
- `Municipio`
- `Nivel`
- `Grado`
- `Sector`
- `Genero`

También se puede descargar una plantilla vacía desde la pantalla inicial.

## Reglas de calidad

Una fila aparece en la auditoría cuando tiene alguno de estos problemas:

- nombre, apellido, identificación, colegio, departamento o municipio faltante;
- identificación con caracteres no numéricos;
- identificación con una longitud fuera de 6 a 12 dígitos;
- identificación repetida dentro del mismo archivo;
- nivel que no puede clasificarse como Junior, Básico, Medio o Avanzado.

Los duplicados se señalan, pero no se eliminan automáticamente: una persona debe decidir si se trata de una inscripción repetida o válida.

## Cruce de calificaciones

En la sección `Cruce de calificaciones`:

1. Carga el consolidado general. No se acepta si aún tiene columnas obligatorias ausentes, identificaciones duplicadas u otros errores.
2. Carga un reporte para cada nivel: Junior, Básico, Medio y Avanzado.
3. La aplicación reconoce reportes de Moodle con columnas como `Número de ID` y `Calificación/80`.
4. El cruce se realiza por identificación y comprueba que el estudiante pertenezca al nivel correcto.
5. Puedes filtrar por código ORM, departamento, municipio, colegio y nivel.
6. Puedes descargar el resultado filtrado, el consolidado completo o archivos separados por nivel en CSV y Excel.

Las filas de resumen de Moodle, como `Promedio general`, se ignoran. Las notas sin inscripción correspondiente se separan en un reporte para revisión y no se agregan silenciosamente al consolidado.

Los archivos de calificaciones no tienen que estar completamente limpios. Las cuentas con identificaciones negativas o alfanuméricas se excluyen como posibles monitores/profesores y aparecen en un reporte de advertencias. Moodle puede usar `-` como calificación cuando no hubo respuesta o presentación; la aplicación lo convierte en nota `0` y lo clasifica como `Sin calificación / no presentó`. Cuando hay varios intentos del mismo ID, se conserva la calificación más alta y los demás intentos se informan como excluidos.

El consolidado final conserva todas las inscripciones. Cuando un estudiante no aparece en los archivos de calificaciones se marca como `No presentó` y recibe nota y porcentaje `0`. El panel muestra cuántos cruces eran posibles, cuántos presentaron, cuántos recibieron cero por ausencia y cuántas calificaciones no encontraron inscripción.

El Excel de resultados contiene únicamente identificación, nombre, apellido, correo, nivel, grado, código ORM, colegio, departamento, ciudad, una columna por prueba y `Nota_Total`. Para procesar una prueba posterior, carga el resultado anterior como consolidado general. Las pruebas existentes se conservan, la prueba nueva se añade y el total se recalcula; una prueba nunca se sobrescribe.

En `examples/merge_test/ejemplo_cruce_prueba_1.zip` hay un conjunto completamente ficticio con el consolidado y los cuatro archivos necesarios para probar este flujo.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

## Estructura relevante

- `scripts/streamlit_dashboard.py`: interfaz web.
- `src/loader.py`: lectura de archivos.
- `src/matcher.py`: reconocimiento seguro de encabezados.
- `src/cleaner.py`: normalización y auditoría.
- `config/normalization.json`: equivalencias de lugares y colegios.
- `tests/`: pruebas automatizadas.

## Camino a producción

Antes de ofrecerla como servicio externo conviene añadir autenticación, almacenamiento cifrado, política de retención/borrado, registro de acciones, copias de seguridad y despliegue HTTPS. La lógica de negocio ya está separada de Streamlit para facilitar una futura migración a una API y una interfaz web independiente.
