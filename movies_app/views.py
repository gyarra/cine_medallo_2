from django.http import HttpResponse

from movies_app.models import Movie, Showtime, Theater


def theater_list(request):
    """Return a list of all active theaters."""
    theaters = Theater.objects.filter(is_active=True).order_by("city", "name")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cines - Cine Medallo</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {
                theme: {
                    extend: {
                        colors: {
                            'brand-red': '#e63946',
                        }
                    }
                }
            }
        </script>
    </head>
    <body class="bg-gray-100 text-gray-800 font-sans">
        <header class="bg-[#1a1a1a] flex items-center justify-between px-10 py-4 border-b border-gray-700">
            <a href="/" class="flex items-center gap-3 no-underline">
                <div class="flex gap-1">
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                </div>
                <div class="text-2xl font-bold tracking-wide">
                    <span class="text-white">CINE</span><span class="text-brand-red">MEDALLO</span>
                </div>
            </a>
            <nav class="flex gap-8">
                <a href="/" class="text-gray-400 no-underline text-sm font-medium tracking-wide uppercase hover:text-white transition-colors">Cartelera</a>
                <a href="/theaters/" class="text-white no-underline text-sm font-medium tracking-wide uppercase">Cines</a>
            </nav>
        </header>
        <div class="p-8 px-10">
            <h2 class="text-gray-800 mt-0 text-2xl font-semibold mb-6">Cines (""" + str(theaters.count()) + """)</h2>
    """

    current_city = None
    for t in theaters:
        if t.city != current_city:
            if current_city is not None:
                html += "</div>"
            current_city = t.city
            html += f'<h3 class="mt-8 first:mt-0 text-gray-600 text-xl border-b-2 border-gray-300 pb-2">{t.city}</h3><div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">'

        html += f"""
        <div class="bg-white p-5 rounded-lg shadow">
            <h3 class="m-0 mb-2 text-lg">
                <a href="/theaters/{t.slug}/" class="text-brand-red no-underline hover:underline">{t.name}</a>
            </h3>
            <div class="text-gray-500 text-sm mb-2 uppercase tracking-wide">{t.chain}</div>
            <div class="text-gray-600 text-sm">{t.address}</div>
            <div class="text-gray-500 text-sm mt-2">
                {t.neighborhood}
                {f' · {t.screen_count} salas' if t.screen_count else ''}
                {f' · <a href="{t.website}" target="_blank" class="text-brand-red hover:underline">Sitio web</a>' if t.website else ''}
            </div>
        </div>
        """

    html += "</div></div></body></html>"
    return HttpResponse(html)


def theater_detail(request, slug):
    """Return details for a single theater by slug."""
    import datetime
    import zoneinfo

    bogota_tz = zoneinfo.ZoneInfo("America/Bogota")

    try:
        t = Theater.objects.get(slug=slug, is_active=True)
    except Theater.DoesNotExist:
        return HttpResponse("<h1>Theater not found</h1>", status=404)

    today = datetime.datetime.now(bogota_tz).date()
    showtimes = (
        Showtime.objects.filter(theater=t, start_date__gte=today)
        .select_related("movie")
        .order_by("start_date", "movie__title_es", "start_time")
    )

    showtimes_by_date: dict[datetime.date, dict[int, dict]] = {}
    for st in showtimes:
        if st.start_date not in showtimes_by_date:
            showtimes_by_date[st.start_date] = {}

        movie_id = st.movie.id  # pyright: ignore[reportAttributeAccessIssue]
        if movie_id not in showtimes_by_date[st.start_date]:
            showtimes_by_date[st.start_date][movie_id] = {
                "movie": st.movie,
                "times": [],
            }
        showtimes_by_date[st.start_date][movie_id]["times"].append(st)

    dias_semana = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

    showtimes_html = ""
    if showtimes_by_date:
        for showtime_date in sorted(showtimes_by_date.keys()):
            movies_for_date = showtimes_by_date[showtime_date]
            dia = dias_semana[showtime_date.weekday()]
            mes = meses[showtime_date.month - 1]
            fecha_str = f"{dia}, {showtime_date.day} de {mes}"
            if showtime_date == today:
                date_label = f"Hoy - {fecha_str}"
            else:
                date_label = fecha_str

            movies_html = ""
            for movie_data in movies_for_date.values():
                movie = movie_data["movie"]
                times = movie_data["times"]
                times_list = []
                for st in times:
                    time_str = st.start_time.strftime("%I:%M %p").lstrip("0")
                    format_str = f' <span class="text-xs opacity-80">({st.format})</span>' if st.format else ""
                    times_list.append(f'<span class="bg-brand-red text-white px-3 py-1.5 rounded text-sm">{time_str}{format_str}</span>')

                poster_html = f'<img class="w-20 h-28 object-cover rounded" src="{movie.poster_url}" alt="{movie.title_es}">' if movie.poster_url else '<div class="w-20 h-28 bg-gray-300 flex items-center justify-center text-gray-500 text-3xl rounded">🎬</div>'
                movies_html += f'''
                <div class="flex gap-4 mb-5 pb-5 border-b border-gray-200 last:border-b-0 last:mb-0 last:pb-0">
                    <a href="/movies/{movie.slug}/" class="no-underline">
                        {poster_html}
                    </a>
                    <div class="flex-1">
                        <div class="font-semibold text-gray-800 mb-3 text-lg"><a href="/movies/{movie.slug}/" class="text-inherit no-underline hover:underline">{movie.title_es}</a></div>
                        <div class="flex flex-wrap gap-2">{" ".join(times_list)}</div>
                    </div>
                </div>
                '''

            showtimes_html += f'''
            <div class="bg-white p-6 rounded-lg mt-6 shadow">
                <h3 class="text-gray-800 text-lg m-0 mb-4 pb-3 border-b-2 border-brand-red">{date_label}</h3>
                {movies_html}
            </div>
            '''
    else:
        showtimes_html = '<p class="text-gray-500 italic mt-6">No hay funciones disponibles</p>'

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{t.name} - Cine Medallo</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {{
                theme: {{
                    extend: {{
                        colors: {{
                            'brand-red': '#e63946',
                        }}
                    }}
                }}
            }}
        </script>
    </head>
    <body class="bg-gray-100 text-gray-800 font-sans">
        <header class="bg-[#1a1a1a] flex items-center justify-between px-10 py-4 border-b border-gray-700">
            <a href="/" class="flex items-center gap-3 no-underline">
                <div class="flex gap-1">
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                </div>
                <div class="text-2xl font-bold tracking-wide">
                    <span class="text-white">CINE</span><span class="text-brand-red">MEDALLO</span>
                </div>
            </a>
            <nav class="flex gap-8">
                <a href="/" class="text-gray-400 no-underline text-sm font-medium tracking-wide uppercase hover:text-white transition-colors">Cartelera</a>
                <a href="/theaters/" class="text-white no-underline text-sm font-medium tracking-wide uppercase">Cines</a>
            </nav>
        </header>
        <div class="max-w-4xl mx-auto p-8 px-10">
            <div class="bg-white p-8 rounded-lg shadow">
                <h2 class="m-0 mb-2 text-gray-800 text-2xl">{t.name}</h2>
                <div class="text-gray-500 text-sm uppercase tracking-wide mb-6">{t.chain}</div>

                <div class="mb-3 text-gray-600"><span class="text-gray-500 font-medium">Dirección:</span> {t.address}</div>
                <div class="mb-3 text-gray-600"><span class="text-gray-500 font-medium">Ciudad:</span> {t.city}</div>
                <div class="mb-3 text-gray-600"><span class="text-gray-500 font-medium">Barrio:</span> {t.neighborhood or 'N/A'}</div>
                <div class="mb-3 text-gray-600"><span class="text-gray-500 font-medium">Teléfono:</span> {t.phone or 'N/A'}</div>
                <div class="mb-3 text-gray-600"><span class="text-gray-500 font-medium">Salas:</span> {t.screen_count or 'N/A'}</div>
                <div class="mb-3 text-gray-600"><span class="text-gray-500 font-medium">Sitio web:</span> {f'<a href="{t.website}" target="_blank" class="text-brand-red hover:underline">{t.website}</a>' if t.website else 'N/A'}</div>
            </div>

            {showtimes_html}
        </div>
    </body>
    </html>
    """
    return HttpResponse(html)


def movie_list(request):
    """Return a list of all movies."""
    movies = Movie.objects.all().order_by("-year", "title_es")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Cine Medallo - Cartelera</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {
                theme: {
                    extend: {
                        colors: {
                            'brand-red': '#e63946',
                        }
                    }
                }
            }
        </script>
    </head>
    <body class="bg-gray-100 text-gray-800 font-sans">
        <header class="bg-[#1a1a1a] flex items-center justify-between px-10 py-4 border-b border-gray-700">
            <a href="/" class="flex items-center gap-3 no-underline">
                <div class="flex gap-1">
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                </div>
                <div class="text-2xl font-bold tracking-wide">
                    <span class="text-white">CINE</span><span class="text-brand-red">MEDALLO</span>
                </div>
            </a>
            <nav class="flex gap-8">
                <a href="/" class="text-white no-underline text-sm font-medium tracking-wide uppercase">Cartelera</a>
                <a href="/theaters/" class="text-gray-400 no-underline text-sm font-medium tracking-wide uppercase hover:text-white transition-colors">Cines</a>
            </nav>
        </header>
        <div class="p-8 px-10">
            <h2 class="text-gray-800 mt-0 text-2xl font-semibold mb-6">En Cartelera (""" + str(movies.count()) + """ películas)</h2>
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-5">
    """

    for m in movies:
        year_str = f"({m.year})" if m.year else ""
        rating_str = f"⭐ {m.tmdb_rating}/10" if m.tmdb_rating else ""
        original_title = f'<div class="text-sm text-gray-500 mb-2 italic">{m.original_title}</div>' if m.original_title and m.original_title != m.title_es else ""
        synopsis = m.synopsis[:200] + "..." if m.synopsis and len(m.synopsis) > 200 else (m.synopsis or "")

        if m.poster_url:
            poster_html = f'<img class="w-full h-96 object-cover bg-gray-300" src="{m.poster_url}" alt="{m.title_es}">'
        else:
            poster_html = '<div class="w-full h-96 bg-gray-300 flex items-center justify-center text-gray-500 text-5xl">🎬</div>'

        links = []
        if m.tmdb_url:
            links.append(f'<a href="{m.tmdb_url}" target="_blank" class="text-brand-red hover:underline">TMDB</a>')
        if m.imdb_url:
            links.append(f'<a href="{m.imdb_url}" target="_blank" class="text-brand-red hover:underline">IMDB</a>')
        links_html = f'<div class="mt-3 text-sm">{" ".join(links)}</div>' if links else ""

        html += f"""
        <div class="bg-white rounded-lg overflow-hidden shadow">
            <a href="/movies/{m.slug}/" class="no-underline text-inherit">
                {poster_html}
            </a>
            <div class="p-4">
                <h2 class="text-lg font-semibold m-0 mb-1 text-gray-800"><a href="/movies/{m.slug}/" class="no-underline text-inherit hover:underline">{m.title_es}</a></h2>
                {original_title}
                <div class="text-sm text-gray-500 mb-2">{year_str}</div>
                <div class="text-sm text-brand-red mb-2">{rating_str}</div>
                <div class="text-sm text-gray-500 leading-relaxed">{synopsis}</div>
                {links_html}
            </div>
        </div>
        """

    html += "</div></div></body></html>"
    return HttpResponse(html)


def movie_detail(request, slug):
    """Return details for a single movie with all showtimes."""
    import datetime
    import zoneinfo

    bogota_tz = zoneinfo.ZoneInfo("America/Bogota")

    try:
        movie = Movie.objects.get(slug=slug)
    except Movie.DoesNotExist:
        return HttpResponse("<h1>Movie not found</h1>", status=404)

    today = datetime.datetime.now(bogota_tz).date()
    tomorrow = today + datetime.timedelta(days=1)
    day_after = today + datetime.timedelta(days=2)

    showtimes = (
        Showtime.objects.filter(
            movie=movie,
            start_date__gte=today,
            start_date__lte=day_after,
        )
        .select_related("theater")
        .order_by("start_date", "theater__name", "start_time")
    )

    year_str = f"({movie.year})" if movie.year else ""
    rating_str = f"⭐ {movie.tmdb_rating}/10" if movie.tmdb_rating else ""
    duration_str = f"{movie.duration_minutes} min" if movie.duration_minutes else ""
    original_title = f"<p><em>{movie.original_title}</em></p>" if movie.original_title and movie.original_title != movie.title_es else ""

    if movie.poster_url:
        poster_html = f'<img class="poster" src="{movie.poster_url}" alt="{movie.title_es}">'
    else:
        poster_html = '<div class="poster-placeholder">🎬</div>'

    links = []
    if movie.tmdb_url:
        links.append(f'<a href="{movie.tmdb_url}" target="_blank">TMDB</a>')
    if movie.imdb_url:
        links.append(f'<a href="{movie.imdb_url}" target="_blank">IMDB</a>')
    links_html = f'<div class="links">{" ".join(links)}</div>' if links else ""

    # Group showtimes by date, then by theater, then by format
    showtimes_by_date: dict[datetime.date, dict[int, dict]] = {}
    for st in showtimes:
        if st.start_date not in showtimes_by_date:
            showtimes_by_date[st.start_date] = {}
        theater_id = st.theater.id
        if theater_id not in showtimes_by_date[st.start_date]:
            showtimes_by_date[st.start_date][theater_id] = {
                "theater": st.theater,
                "formats": {},
            }
        format_key = st.format or "Standard"
        if format_key not in showtimes_by_date[st.start_date][theater_id]["formats"]:
            showtimes_by_date[st.start_date][theater_id]["formats"][format_key] = []
        showtimes_by_date[st.start_date][theater_id]["formats"][format_key].append(st)

    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    dias_semana_full = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

    # Build date tabs
    available_dates = sorted(showtimes_by_date.keys()) if showtimes_by_date else []
    date_tabs_html = ""
    initial_date_title = ""
    if available_dates:
        for i, d in enumerate(available_dates):
            dia_short = dias_semana[d.weekday()]
            dia_full = dias_semana_full[d.weekday()]
            mes = meses[d.month - 1]
            if d == today:
                tab_label = "Hoy"
                tab_sub = f"{dia_short} {d.day}"
                full_title = f"Hoy - {dia_full}, {d.day} de {mes}"
            elif d == tomorrow:
                tab_label = "Mañana"
                tab_sub = f"{dia_short} {d.day}"
                full_title = f"Mañana - {dia_full}, {d.day} de {mes}"
            else:
                tab_label = dia_short
                tab_sub = str(d.day)
                full_title = f"{dia_full}, {d.day} de {mes}"
            if i == 0:
                initial_date_title = full_title
            active_class = "bg-gray-900 text-white" if i == 0 else "bg-white text-gray-600 hover:bg-gray-50"
            date_tabs_html += f'<button class="date-tab px-4 py-2 rounded-lg text-center min-w-[70px] border border-gray-200 {active_class}" data-date="{d.isoformat()}" data-title="{full_title}"><div class="text-sm font-medium">{tab_label}</div><div class="text-xs opacity-70">{tab_sub}</div></button>'

    showtimes_html = ""
    if showtimes_by_date:
        # Generate HTML for each date (hidden by default except first)
        for date_idx, showtime_date in enumerate(available_dates):
            theaters_for_date = showtimes_by_date[showtime_date]

            theaters_html = ""
            for theater_data in theaters_for_date.values():
                theater = theater_data["theater"]
                formats = theater_data["formats"]

                formats_html = ""
                for format_name, times in formats.items():
                    times_list = []
                    for st in times:
                        time_str = st.start_time.strftime("%I:%M %p").lstrip("0").upper()
                        times_list.append(f'<span class="px-3 py-2 border border-gray-300 rounded text-sm text-gray-700">{time_str}</span>')
                    formats_html += f'''
                    <div class="flex items-start gap-4 mb-3 last:mb-0">
                        <div class="text-sm text-gray-500 w-28 pt-2 shrink-0">{format_name}:</div>
                        <div class="flex flex-wrap gap-2">{" ".join(times_list)}</div>
                    </div>
                    '''

                theaters_html += f'''
                <div class="py-5 border-b border-gray-100 last:border-b-0">
                    <div class="flex items-start justify-between mb-4">
                        <div>
                            <a href="/theaters/{theater.slug}/" class="text-gray-900 font-semibold text-base no-underline hover:underline">{theater.name} ›</a>
                            <div class="text-sm text-gray-500 mt-1">{theater.address}, {theater.city}</div>
                        </div>
                    </div>
                    {formats_html}
                </div>
                '''

            display_class = "" if date_idx == 0 else "hidden"
            showtimes_html += f'''
            <div class="date-content {display_class}" data-date="{showtime_date.isoformat()}">
                {theaters_html}
            </div>
            '''
    else:
        showtimes_html = '<p class="text-gray-500 italic">No hay funciones disponibles</p>'

    # JavaScript for tab switching
    tab_script = """
    <script>
        document.querySelectorAll('.date-tab').forEach(tab => {
            tab.addEventListener('click', function() {
                const date = this.dataset.date;
                document.querySelectorAll('.date-tab').forEach(t => {
                    t.classList.remove('bg-gray-900', 'text-white');
                    t.classList.add('bg-white', 'text-gray-600');
                });
                this.classList.remove('bg-white', 'text-gray-600');
                this.classList.add('bg-gray-900', 'text-white');
                document.querySelectorAll('.date-content').forEach(c => c.classList.add('hidden'));
                document.querySelector(`.date-content[data-date="${date}"]`).classList.remove('hidden');
                document.getElementById('date-title').textContent = this.dataset.title;
            });
        });
    </script>
    """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{movie.title_es} - Cine Medallo</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
            tailwind.config = {{
                theme: {{
                    extend: {{
                        colors: {{
                            'brand-red': '#e63946',
                        }}
                    }}
                }}
            }}
        </script>
    </head>
    <body class="bg-gray-100 text-gray-800 font-sans">
        <header class="bg-[#1a1a1a] flex items-center justify-between px-10 py-4 border-b border-gray-700">
            <a href="/" class="flex items-center gap-3 no-underline">
                <div class="flex gap-1">
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                    <span class="block w-2 h-10 bg-brand-red rounded-sm"></span>
                </div>
                <div class="text-2xl font-bold tracking-wide">
                    <span class="text-white">CINE</span><span class="text-brand-red">MEDALLO</span>
                </div>
            </a>
            <nav class="flex gap-8">
                <a href="/" class="text-gray-400 no-underline text-sm font-medium tracking-wide uppercase hover:text-white transition-colors">Cartelera</a>
                <a href="/theaters/" class="text-gray-400 no-underline text-sm font-medium tracking-wide uppercase hover:text-white transition-colors">Cines</a>
            </nav>
        </header>
        <div class="max-w-5xl mx-auto p-8 px-10">
            <div class="flex gap-8 bg-white p-6 rounded-lg shadow max-md:flex-col">
                {poster_html}
                <div class="flex-1 flex flex-col">
                    <h1 class="m-0 mb-2 text-gray-800 text-3xl">{movie.title_es}</h1>
                    {original_title}
                    <div class="text-gray-500 text-sm mb-4">
                        {year_str} {f"· {duration_str}" if duration_str else ""} {f"· {movie.genre}" if movie.genre else ""} {f"· {movie.age_rating_colombia}" if movie.age_rating_colombia else ""}
                    </div>
                    <div class="text-brand-red">{rating_str}</div>
                    <div class="text-gray-600 leading-relaxed mt-4 order-1 md:order-3">{movie.synopsis or ""}</div>
                    {f'<div class="mt-4 text-gray-600 text-sm order-2 md:order-1"><span class="font-semibold text-gray-700">Director:</span> {movie.director}</div>' if movie.director else ""}
                    {f'<div class="mt-2 text-gray-600 text-sm order-3 md:order-2"><span class="font-semibold text-gray-700">Reparto:</span> {movie.cast_summary}</div>' if movie.cast_summary else ""}
                    <div class="order-4">{links_html}</div>
                </div>
            </div>

            <div class="bg-white p-6 rounded-lg shadow mt-6">
                <h3 id="date-title" class="text-gray-900 text-lg font-semibold m-0 mb-4">{initial_date_title}</h3>
                <div class="flex gap-2">
                    {date_tabs_html}
                </div>
            </div>

            <div class="bg-white p-6 rounded-lg shadow mt-4">
                {showtimes_html}
            </div>
        </div>
        {tab_script}
    </body>
    </html>
    """
    return HttpResponse(html)

