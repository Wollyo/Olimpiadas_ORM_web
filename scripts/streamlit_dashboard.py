"""Dashboard web para limpiar y auditar inscripciones de las Olimpiadas."""

from __future__ import annotations

import base64
import sys
from io import BytesIO
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
LOGO_PATH = ROOT / "assets" / "univalle_logo.png"
STYLES_PATH = ROOT / "assets" / "styles.css"
RESULT_LEVELS = ("Junior", "Básico", "Medio", "Avanzado")
with Image.open(LOGO_PATH) as logo_file:
    PAGE_ICON = logo_file.copy()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cleaner import (  # noqa: E402
    CANONICAL_DEPARTMENT,
    CANONICAL_ID,
    CANONICAL_MUNICIPALITY,
    CANONICAL_SCHOOL,
    Cleaner,
    detect_problems,
)
from src.loader import DataLoadError, DataLoader  # noqa: E402
from src.results_merger import (  # noqa: E402
    GradeFileError,
    build_results_export,
    combine_grade_files,
    merge_with_registrations,
    prepare_grade_file,
)
from src.utils import make_unique_column_names  # noqa: E402


st.set_page_config(
    page_title="Centro de control ORM · Universidad del Valle",
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_brand_styles() -> None:
    styles = STYLES_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{styles}</style>", unsafe_allow_html=True)


def render_brand_header() -> None:
    logo_data = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    st.markdown(
        f"""
        <section class="uv-hero" aria-label="Centro de control ORM">
          <div class="uv-hero-logo">
            <img src="data:image/png;base64,{logo_data}" alt="Universidad del Valle">
          </div>
          <div>
            <div class="uv-eyebrow">Universidad del Valle · Olimpiadas Regionales</div>
            <h1>Centro de control <span>ORM</span></h1>
            <p>Calidad de datos, auditoría de inscripciones y consolidación de
            resultados en un solo espacio de trabajo.</p>
            <div class="uv-status"><span class="uv-status-dot"></span>Sistema listo para procesar</div>
          </div>
        </section>
        <div class="uv-privacy">
          <span aria-hidden="true">◆</span>
          <span><strong>Tratamiento responsable de datos.</strong> Los archivos pueden
          contener información personal; evita compartir exportaciones o publicarlas.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    st.markdown(
        """
        <footer class="uv-footer" aria-label="Crédito del creador">
          <span>Creado por</span>
          <strong>Wolyo</strong>
        </footer>
        """,
        unsafe_allow_html=True,
    )


def load_uploaded_file(file_name: str, content: bytes) -> pd.DataFrame:
    return DataLoader.from_bytes(file_name, content)


def prepare_data(frame: pd.DataFrame):
    return Cleaner.prepare(frame)


def find_problems(frame: pd.DataFrame) -> pd.DataFrame:
    return detect_problems(frame)


def excel_bytes(frame: pd.DataFrame, sheet_name: str) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name=sheet_name[:31])
    return buffer.getvalue()


def results_excel_bytes(frame: pd.DataFrame) -> bytes:
    """Crea un consolidado con una hoja general y una por cada nivel."""
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="General")
        for level in RESULT_LEVELS:
            level_frame = frame[frame["Nivel"].eq(level)]
            level_frame.to_excel(writer, index=False, sheet_name=level)
    return buffer.getvalue()


def csv_bytes(frame: pd.DataFrame) -> bytes:
    # El BOM permite que Excel para Windows reconozca correctamente los acentos.
    return frame.to_csv(index=False).encode("utf-8-sig")


def presentation_frame(frame: pd.DataFrame, *, audit: bool = False) -> pd.DataFrame:
    """Quita columnas totalmente vacías y reemplaza nombres técnicos."""
    # Estas columnas son necesarias para filtros y métricas, pero no forman
    # parte del archivo que ve o descarga el usuario.
    presented = frame.drop(
        columns=["tipo_colegio", "genero_normalizado"],
        errors="ignore",
    ).copy()
    empty_columns = [
        column
        for column in presented.columns
        if presented[column].isna().all()
        or presented[column].fillna("").astype(str).str.strip().eq("").all()
    ]
    if empty_columns:
        presented = presented.drop(columns=empty_columns)

    presented = presented.rename(
        columns={
            "_fila_origen": "Fila de origen",
            "columnas_con_error": "Columnas con error",
            "errores": "Detalle del error",
        }
    )
    # El nombre legible de una columna técnica puede coincidir con uno que ya
    # venía en el archivo. Se conservan ambas con sufijos antes de usar PyArrow.
    presented.columns = make_unique_column_names(presented.columns)

    if audit:
        preferred = ["Fila de origen", "Columnas con error", "Detalle del error"]
        first = [column for column in preferred if column in presented.columns]
        remaining = [column for column in presented.columns if column not in first]
        presented = presented[[*first, *remaining]]
    return presented


def filter_selectbox(
    frame: pd.DataFrame,
    column: str,
    label: str,
    *,
    key: str,
) -> pd.DataFrame:
    values = frame[column].fillna("").astype(str).str.strip()
    options = sorted(value for value in values.unique().tolist() if value)
    selection = st.sidebar.selectbox(label, ["(Todos)", *options], key=key)
    if selection == "(Todos)":
        return frame
    return frame[values == selection]


def clear_filters() -> None:
    for key in ("department", "municipality", "school", "level", "school_type", "gender"):
        st.session_state[key] = "(Todos)"


def clear_result_filters() -> None:
    for key in (
        "result_department",
        "result_municipality",
        "result_school",
        "result_code",
        "result_level",
    ):
        st.session_state[key] = "(Todos)"


def show_start_screen() -> None:
    st.info("Sube un archivo para comenzar. Los datos se procesan durante esta sesión.")
    st.markdown(
        """
        La aplicación reconoce variantes comunes de encabezados, pero funciona mejor
        cuando el archivo incluye: **Identificación, Nombres, Apellidos, Colegio,
        Departamento, Municipio, Nivel, Grado, Sector y Género**.
        """
    )
    template = pd.DataFrame(
        columns=[
            "Numero identificacion",
            "Nombres",
            "Apellidos",
            "Nombre del colegio o institución educativa",
            "Departamento",
            "Municipio",
            "Nivel",
            "Grado",
            "Sector",
            "Genero",
        ]
    )
    st.download_button(
        "Descargar plantilla CSV",
        data=csv_bytes(template),
        file_name="plantilla_inscripciones.csv",
        mime="text/csv",
    )


def render_metrics(frame: pd.DataFrame, problem_count: int) -> None:
    metrics = st.columns(6)
    metrics[0].metric("Registros visibles", len(frame))
    metrics[1].metric("Con problemas", problem_count)
    metrics[2].metric("Colegios", frame[CANONICAL_SCHOOL].replace("", pd.NA).nunique())
    metrics[3].metric("Municipios", frame[CANONICAL_MUNICIPALITY].replace("", pd.NA).nunique())
    metrics[4].metric("Hombres", int(frame["genero_normalizado"].eq("Hombre").sum()))
    metrics[5].metric("Mujeres", int(frame["genero_normalizado"].eq("Mujer").sum()))


def render_red_bar_chart(values: pd.Series) -> None:
    """Renderiza barras con una escala vino-rojo sobria sobre el tema oscuro."""
    chart_data = values.rename_axis("categoria").reset_index(name="cantidad")
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X(
                "categoria:N",
                sort=None,
                title=None,
                axis=alt.Axis(labelAngle=-90, labelLimit=115),
            ),
            y=alt.Y("cantidad:Q", title=None),
            color=alt.Color(
                "cantidad:Q",
                scale=alt.Scale(range=["#64171C", "#98212A", "#C92A34"]),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("categoria:N", title="Categoría"),
                alt.Tooltip("cantidad:Q", title="Registros", format=","),
            ],
        )
        .properties(height=270)
        .configure_axis(
            domainColor="#3A3B42",
            gridColor="#292A30",
            labelColor="#E2E2E6",
            tickColor="#3A3B42",
            titleColor="#E2E2E6",
        )
        .configure_view(strokeOpacity=0)
    )
    st.altair_chart(chart, use_container_width=True)


def render_charts(frame: pd.DataFrame) -> None:
    st.subheader("Distribuciones")
    level_col, municipality_col, sector_col = st.columns(3)
    with level_col:
        st.caption("Por nivel")
        render_red_bar_chart(
            frame["Nivel"].replace("", "Sin dato").value_counts()
        )
    with municipality_col:
        st.caption("Principales municipios")
        render_red_bar_chart(
            frame[CANONICAL_MUNICIPALITY]
            .replace("", "Sin dato")
            .value_counts()
            .head(15)
        )
    with sector_col:
        st.caption("Por tipo de colegio")
        render_red_bar_chart(frame["tipo_colegio"].value_counts())


def render_registration_section() -> None:
    st.subheader("Limpieza y auditoría de inscripciones")
    uploaded_file = st.file_uploader(
        "Archivo de inscripciones",
        type=["csv", "xlsx"],
        help="Se admiten CSV con coma o punto y coma y archivos XLSX.",
        key="registration_file",
    )
    if uploaded_file is None:
        show_start_screen()
        return

    try:
        with st.spinner("Leyendo y validando el archivo..."):
            raw_frame = load_uploaded_file(uploaded_file.name, uploaded_file.getvalue())
            cleaned_frame, detected = prepare_data(raw_frame)
            problems = find_problems(cleaned_frame)
    except DataLoadError as exc:
        st.error(str(exc))
        return
    except Exception:
        st.error("El archivo no pudo procesarse. Revisa sus encabezados y formato.")
        return

    if cleaned_frame.empty:
        st.error("El archivo no contiene registros.")
        return

    missing_columns = detected.required_missing()
    if missing_columns:
        st.error(
            "No se reconocieron estas columnas obligatorias: "
            + ", ".join(missing_columns)
            + ". Se conservará el archivo, pero esos campos quedarán vacíos."
        )
    else:
        st.success(f"Archivo procesado correctamente: {len(cleaned_frame):,} registros.")

    st.sidebar.header("Filtros de inscripciones")
    st.sidebar.button(
        "Limpiar filtros",
        on_click=clear_filters,
        use_container_width=True,
    )
    filtered = cleaned_frame
    filtered = filter_selectbox(filtered, CANONICAL_DEPARTMENT, "Departamento", key="department")
    filtered = filter_selectbox(filtered, CANONICAL_MUNICIPALITY, "Municipio", key="municipality")
    filtered = filter_selectbox(filtered, CANONICAL_SCHOOL, "Colegio", key="school")
    filtered = filter_selectbox(filtered, "Nivel", "Nivel", key="level")
    filtered = filter_selectbox(filtered, "tipo_colegio", "Tipo de colegio", key="school_type")
    filtered = filter_selectbox(filtered, "genero_normalizado", "Género", key="gender")

    st.sidebar.metric("Registros visibles", len(filtered))

    visible_rows = set(filtered["_fila_origen"].tolist())
    filtered_problems = (
        problems[problems["_fila_origen"].isin(visible_rows)].copy()
        if not problems.empty
        else problems.copy()
    )
    duplicate_rows = (
        filtered_problems["errores"]
        .str.contains("Identificación duplicada", regex=False)
        .sum()
        if not filtered_problems.empty
        else 0
    )
    non_numeric_rows = (
        filtered_problems["errores"]
        .str.contains("Identificación no numérica", regex=False)
        .sum()
        if not filtered_problems.empty
        else 0
    )

    render_metrics(filtered, len(filtered_problems))
    quality_a, quality_b, quality_c = st.columns(3)
    quality_a.metric("Filas con ID duplicado", int(duplicate_rows))
    quality_b.metric("ID no numérico", int(non_numeric_rows))
    quality_c.metric("Nivel no reconocido", int(filtered["Nivel"].eq("No definido").sum()))

    if filtered.empty:
        st.warning("No hay registros que coincidan con los filtros seleccionados.")
    else:
        render_charts(filtered)
        st.subheader("Registros")
        with st.expander("¿Qué significan las columnas añadidas?"):
            st.markdown(
                """
                - **Fila de origen:** número de la fila en el archivo que subiste.
                - **Tipo de colegio y género:** sus valores se corrigen directamente
                  en las columnas originales, sin crear columnas adicionales.
                - **Nivel:** clasificación uniforme usada por los filtros y gráficos.
                """
            )
        visible_data = presentation_frame(filtered)
        st.dataframe(visible_data, use_container_width=True, hide_index=True)

        download_csv, download_excel = st.columns(2)
        download_csv.download_button(
            "Descargar CSV filtrado",
            data=csv_bytes(visible_data),
            file_name="inscripciones_filtradas.csv",
            mime="text/csv",
            use_container_width=True,
        )
        download_excel.download_button(
            "Descargar Excel filtrado",
            data=excel_bytes(visible_data, "Inscripciones"),
            file_name="inscripciones_filtradas.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.divider()
    st.subheader("Auditoría de calidad")
    st.caption(
        "La tabla muestra solamente los problemas de los registros visibles. "
        "Los duplicados se comparan contra el archivo completo y _fila_origen indica "
        "dónde revisar el dato original."
    )
    if filtered_problems.empty:
        st.success("No se detectaron problemas en los registros visibles.")
    else:
        st.warning(
            f"Se detectaron {len(filtered_problems):,} filas visibles que requieren revisión."
        )
        visible_problems = presentation_frame(filtered_problems, audit=True)
        st.dataframe(visible_problems, use_container_width=True, hide_index=True)
        problems_csv, problems_excel = st.columns(2)
        problems_csv.download_button(
            "Descargar problemas en CSV",
            data=csv_bytes(visible_problems),
            file_name="problemas_inscripciones.csv",
            mime="text/csv",
            use_container_width=True,
        )
        problems_excel.download_button(
            "Descargar problemas en Excel",
            data=excel_bytes(visible_problems, "Problemas"),
            file_name="problemas_inscripciones.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


def render_results_section() -> None:
    st.subheader("Cruce del consolidado con calificaciones")
    st.markdown(
        "Carga primero el consolidado limpio y después un archivo de calificaciones "
        "para cada nivel. El cruce se realiza exclusivamente por identificación."
    )

    general_file = st.file_uploader(
        "1. Consolidado general limpio",
        type=["csv", "xlsx"],
        key="merge_general_file",
    )
    if general_file is None:
        st.info("El consolidado debe pasar todas las reglas de calidad antes de continuar.")
        return

    try:
        raw_general = load_uploaded_file(general_file.name, general_file.getvalue())
        registrations, detected = prepare_data(raw_general)
        registration_problems = find_problems(registrations)
    except DataLoadError as exc:
        st.error(str(exc))
        return
    except Exception:
        st.error("No se pudo procesar el consolidado general.")
        return

    missing_columns = detected.required_missing()
    if missing_columns or not registration_problems.empty:
        details = []
        if missing_columns:
            details.append("columnas no reconocidas: " + ", ".join(missing_columns))
        if not registration_problems.empty:
            details.append(f"{len(registration_problems):,} filas con problemas")
        st.error(
            "El consolidado no fue aceptado porque todavía necesita limpieza ("
            + "; ".join(details)
            + "). Corrígelo en la primera sección y vuelve a cargarlo."
        )
        if not registration_problems.empty:
            rejected = presentation_frame(registration_problems, audit=True)
            st.dataframe(rejected, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar errores del consolidado",
                data=excel_bytes(rejected, "Errores"),
                file_name="errores_consolidado_general.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        return

    st.success(f"Consolidado aceptado: {len(registrations):,} inscripciones sin errores.")
    st.markdown("#### 2. Archivos de calificaciones por nivel")
    st.caption(
        "Estos archivos pueden contener monitores, profesores, filas resumen o intentos "
        "repetidos. La aplicación los separa y continúa con las calificaciones válidas."
    )

    levels = list(RESULT_LEVELS)
    upload_columns = st.columns(2)
    uploaded_grades = {}
    for index, level in enumerate(levels):
        with upload_columns[index % 2]:
            uploaded_grades[level] = st.file_uploader(
                f"Calificaciones — {level}",
                type=["csv", "xlsx"],
                key=f"grade_file_{level}",
            )

    prepared_files = []
    excluded_reports = []
    grade_errors = []
    for level, uploaded in uploaded_grades.items():
        if uploaded is None:
            continue
        try:
            grade_frame = load_uploaded_file(uploaded.name, uploaded.getvalue())
            prepared = prepare_grade_file(
                grade_frame,
                level=level,
                file_name=uploaded.name,
            )
            prepared_files.append(prepared)
            if not prepared.excluded_rows.empty:
                excluded_reports.append(prepared.excluded_rows)
            st.success(
                f"{level}: {len(prepared.frame):,} calificaciones válidas "
                f"({prepared.test_name})."
            )
            if not prepared.excluded_rows.empty:
                st.warning(
                    f"{level}: se excluyeron {len(prepared.excluded_rows):,} registros "
                    "no estudiantiles, inválidos o repetidos."
                )
            if prepared.administrative_rows:
                st.caption(
                    f"{level}: {prepared.administrative_rows} fila(s) resumen de Moodle ignorada(s)."
                )
        except (DataLoadError, GradeFileError) as exc:
            grade_errors.append(str(exc))
            st.error(str(exc))

    if excluded_reports:
        excluded_all = pd.concat(excluded_reports, ignore_index=True)
        with st.expander(
            f"Advertencias de los archivos de notas ({len(excluded_all):,} excluidos)",
            expanded=True,
        ):
            st.dataframe(excluded_all, use_container_width=True, hide_index=True)
            st.download_button(
                "Descargar registros excluidos",
                data=excel_bytes(excluded_all, "Excluidos"),
                file_name="registros_excluidos_calificaciones.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

    if grade_errors:
        return
    if len(prepared_files) < len(levels):
        st.info(f"Faltan {len(levels) - len(prepared_files)} archivos de nivel para hacer el cruce.")
        return

    try:
        grades, test_name = combine_grade_files(prepared_files)
        merged, unmatched, mismatches = merge_with_registrations(registrations, grades)
    except (GradeFileError, pd.errors.MergeError) as exc:
        st.error(str(exc))
        return

    if not mismatches.empty:
        st.error(
            f"Hay {len(mismatches):,} estudiantes cargados en un archivo de nivel "
            "diferente al nivel del consolidado. Corrige los archivos antes de continuar."
        )
        mismatch_columns = [
            column
            for column in (
                CANONICAL_ID,
                "Nombres",
                "Apellidos",
                "Nivel",
                "Nivel del archivo de notas",
            )
            if column in mismatches.columns
        ]
        mismatch_view = mismatches[mismatch_columns]
        st.dataframe(mismatch_view, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar niveles incorrectos",
            data=excel_bytes(mismatch_view, "Niveles incorrectos"),
            file_name="niveles_incorrectos.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        return

    try:
        result_output = build_results_export(merged, test_name)
    except GradeFileError as exc:
        st.error(str(exc))
        return

    if not unmatched.empty:
        st.warning(
            f"{len(unmatched):,} calificaciones no tienen una identificación "
            "correspondiente en el consolidado y no se incluyeron en el resultado final."
        )
        unmatched_view = presentation_frame(unmatched)
        st.dataframe(unmatched_view, use_container_width=True, hide_index=True)
        st.download_button(
            "Descargar calificaciones sin inscripción",
            data=excel_bytes(unmatched_view, "Sin inscripción"),
            file_name="calificaciones_sin_inscripcion.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    else:
        st.success("Todas las calificaciones cargadas encontraron su inscripción correspondiente.")

    total_presented = int(merged["Presentó la prueba"].sum())
    total_absent = len(merged) - total_presented
    st.info(
        f"Verificación del cruce: {len(merged):,} inscripciones posibles; "
        f"{total_presented:,} tienen calificación y {total_absent:,} aparecen sin "
        "calificación o no presentaron. A estos últimos se les asignó nota 0."
    )

    st.sidebar.header("Filtros del consolidado con notas")
    st.sidebar.button(
        "Limpiar filtros de notas",
        on_click=clear_result_filters,
        use_container_width=True,
    )
    filtered = result_output
    filtered = filter_selectbox(
        filtered,
        "Departamento",
        "Departamento",
        key="result_department",
    )
    filtered = filter_selectbox(
        filtered,
        "Ciudad",
        "Municipio / ciudad",
        key="result_municipality",
    )
    filtered = filter_selectbox(
        filtered,
        "Colegio",
        "Colegio",
        key="result_school",
    )
    filtered = filter_selectbox(
        filtered,
        "Codigo ORM",
        "Código ORM",
        key="result_code",
    )
    filtered = filter_selectbox(
        filtered,
        "Nivel",
        "Nivel",
        key="result_level",
    )

    presented_ids = set(
        merged.loc[merged["Presentó la prueba"], CANONICAL_ID].astype(str)
    )
    presented_mask = filtered["Número de ID"].astype(str).isin(presented_ids)
    with_grade = int(presented_mask.sum())
    without_grade = len(filtered) - with_grade
    average = filtered[test_name].mean()
    presented_average = filtered.loc[presented_mask, test_name].mean()
    metric_columns = st.columns(6)
    metric_columns[0].metric("Registros visibles", len(filtered))
    metric_columns[1].metric("Con calificación", with_grade)
    metric_columns[2].metric("Sin calificación / no presentaron", without_grade)
    metric_columns[3].metric(
        "Promedio general (incluye 0)",
        f"{average:.2f}" if pd.notna(average) else "—",
    )
    metric_columns[4].metric(
        "Promedio de quienes presentaron",
        f"{presented_average:.2f}" if pd.notna(presented_average) else "—",
    )
    metric_columns[5].metric("Notas sin inscripción", len(unmatched))

    st.subheader(f"Consolidado final — {test_name}")
    filtered_output = filtered
    full_output = result_output
    st.dataframe(filtered_output, use_container_width=True, hide_index=True)

    st.markdown("#### Descargas")
    filtered_csv, filtered_excel, full_csv, full_excel = st.columns(4)
    file_tag = test_name.lower().replace(" ", "_")
    filtered_csv.download_button(
        "CSV filtrado",
        data=csv_bytes(filtered_output),
        file_name=f"consolidado_{file_tag}_filtrado.csv",
        mime="text/csv",
        use_container_width=True,
    )
    filtered_excel.download_button(
        "Excel filtrado",
        data=excel_bytes(filtered_output, "Filtrado"),
        file_name=f"consolidado_{file_tag}_filtrado.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    full_csv.download_button(
        "CSV completo",
        data=csv_bytes(full_output),
        file_name=f"consolidado_{file_tag}_completo.csv",
        mime="text/csv",
        use_container_width=True,
    )
    full_excel.download_button(
        "Excel completo",
        data=results_excel_bytes(full_output),
        file_name=f"consolidado_{file_tag}_completo.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    with st.expander("Descargas separadas por nivel"):
        for level in levels:
            level_output = result_output[result_output["Nivel"] == level]
            label, csv_download, excel_download = st.columns([2, 1, 1])
            label.write(f"**{level}:** {len(level_output):,} registros")
            csv_download.download_button(
                "CSV",
                data=csv_bytes(level_output),
                file_name=f"{file_tag}_{level.lower()}.csv",
                mime="text/csv",
                key=f"download_csv_{level}",
                use_container_width=True,
            )
            excel_download.download_button(
                "Excel",
                data=excel_bytes(level_output, level),
                file_name=f"{file_tag}_{level.lower()}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_excel_{level}",
                use_container_width=True,
            )


def main() -> None:
    inject_brand_styles()
    st.logo(str(LOGO_PATH), size="large")
    render_brand_header()
    section = st.segmented_control(
        "Sección",
        options=["Limpieza de inscripciones", "Cruce de calificaciones"],
        default="Limpieza de inscripciones",
        selection_mode="single",
        key="main_section",
        label_visibility="collapsed",
    )
    if section == "Cruce de calificaciones":
        render_results_section()
    else:
        render_registration_section()
    render_footer()


if __name__ == "__main__":
    main()
