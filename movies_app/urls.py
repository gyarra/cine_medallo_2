from django.urls import path

from movies_app import views

urlpatterns = [
    path("movies/", views.movie_list, name="movie_list"),
    path("theaters/", views.theater_list, name="theater_list"),
    path("theaters/<slug:slug>/", views.theater_detail, name="theater_detail"),
]
