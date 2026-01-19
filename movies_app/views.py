from django.http import HttpResponse

from movies_app.models import Movie, Theater


def theater_list(request):
    """Return a list of all active theaters."""
    theaters = Theater.objects.filter(is_active=True).order_by("city", "name")

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Theaters</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; }
            h1 { color: #333; }
            .theater { border: 1px solid #ddd; padding: 16px; margin-bottom: 16px; border-radius: 8px; }
            .theater h2 { margin: 0 0 8px 0; font-size: 18px; }
            .theater h2 a { color: #0066cc; text-decoration: none; }
            .theater h2 a:hover { text-decoration: underline; }
            .chain { color: #666; font-size: 14px; margin-bottom: 8px; }
            .address { color: #444; }
            .details { color: #666; font-size: 14px; margin-top: 8px; }
        </style>
    </head>
    <body>
        <h1>Theaters (""" + str(theaters.count()) + """)</h1>
    """

    current_city = None
    for t in theaters:
        if t.city != current_city:
            if current_city is not None:
                html += "</div>"
            current_city = t.city
            html += f"<h2 style='margin-top: 32px; color: #555;'>{t.city}</h2><div>"

        html += f"""
        <div class="theater">
            <h2><a href="/api/theaters/{t.slug}/">{t.name}</a></h2>
            <div class="chain">{t.chain}</div>
            <div class="address">{t.address}</div>
            <div class="details">
                {t.neighborhood}
                {f' · {t.screen_count} screens' if t.screen_count else ''}
                {f' · <a href="{t.website}" target="_blank">Website</a>' if t.website else ''}
            </div>
        </div>
        """

    html += "</div></body></html>"
    return HttpResponse(html)


def theater_detail(request, slug):
    """Return details for a single theater by slug."""
    try:
        t = Theater.objects.get(slug=slug, is_active=True)
    except Theater.DoesNotExist:
        return HttpResponse("<h1>Theater not found</h1>", status=404)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{t.name}</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; }}
            h1 {{ color: #333; margin-bottom: 8px; }}
            .chain {{ color: #666; font-size: 18px; margin-bottom: 24px; }}
            .info {{ margin-bottom: 12px; }}
            .label {{ color: #666; font-weight: 500; }}
            a {{ color: #0066cc; }}
            .back {{ margin-top: 32px; }}
        </style>
    </head>
    <body>
        <h1>{t.name}</h1>
        <div class="chain">{t.chain}</div>

        <div class="info"><span class="label">Address:</span> {t.address}</div>
        <div class="info"><span class="label">City:</span> {t.city}</div>
        <div class="info"><span class="label">Neighborhood:</span> {t.neighborhood or 'N/A'}</div>
        <div class="info"><span class="label">Phone:</span> {t.phone or 'N/A'}</div>
        <div class="info"><span class="label">Screens:</span> {t.screen_count or 'N/A'}</div>
        <div class="info"><span class="label">Website:</span> {f'<a href="{t.website}" target="_blank">{t.website}</a>' if t.website else 'N/A'}</div>

        <div class="back"><a href="/api/theaters/">← Back to all theaters</a></div>
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
        <title>Movies</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 40px; background: #f5f5f5; }
            h1 { color: #333; }
            .movies { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
            .movie { background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            .movie-poster { width: 100%; height: 400px; object-fit: cover; background: #ddd; }
            .movie-poster-placeholder { width: 100%; height: 400px; background: #e0e0e0; display: flex; align-items: center; justify-content: center; color: #999; font-size: 48px; }
            .movie-info { padding: 16px; }
            .movie-title { font-size: 18px; font-weight: 600; margin: 0 0 4px 0; color: #333; }
            .movie-original { font-size: 14px; color: #666; margin-bottom: 8px; font-style: italic; }
            .movie-year { font-size: 14px; color: #888; margin-bottom: 8px; }
            .movie-rating { font-size: 14px; color: #f5c518; margin-bottom: 8px; }
            .movie-synopsis { font-size: 13px; color: #555; line-height: 1.4; }
            .movie-links { margin-top: 12px; font-size: 13px; }
            .movie-links a { color: #0066cc; text-decoration: none; margin-right: 12px; }
            .movie-links a:hover { text-decoration: underline; }
        </style>
    </head>
    <body>
        <h1>🎬 Movies (""" + str(movies.count()) + """)</h1>
        <div class="movies">
    """

    for m in movies:
        year_str = f"({m.year})" if m.year else ""
        rating_str = f"⭐ {m.tmdb_rating}/10" if m.tmdb_rating else ""
        original_title = f'<div class="movie-original">{m.original_title}</div>' if m.original_title and m.original_title != m.title_es else ""
        synopsis = m.synopsis[:200] + "..." if m.synopsis and len(m.synopsis) > 200 else (m.synopsis or "")

        if m.poster_url:
            poster_html = f'<img class="movie-poster" src="{m.poster_url}" alt="{m.title_es}">'
        else:
            poster_html = '<div class="movie-poster-placeholder">🎬</div>'

        links = []
        if m.tmdb_url:
            links.append(f'<a href="{m.tmdb_url}" target="_blank">TMDB</a>')
        if m.imdb_url:
            links.append(f'<a href="{m.imdb_url}" target="_blank">IMDB</a>')
        links_html = f'<div class="movie-links">{" ".join(links)}</div>' if links else ""

        html += f"""
        <div class="movie">
            {poster_html}
            <div class="movie-info">
                <h2 class="movie-title">{m.title_es}</h2>
                {original_title}
                <div class="movie-year">{year_str}</div>
                <div class="movie-rating">{rating_str}</div>
                <div class="movie-synopsis">{synopsis}</div>
                {links_html}
            </div>
        </div>
        """

    html += "</div></body></html>"
    return HttpResponse(html)

