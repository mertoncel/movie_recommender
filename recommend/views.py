from django.contrib.auth import authenticate, login
from django.contrib.auth import logout
from django.shortcuts import render, get_object_or_404, redirect
from .forms import *
from django.http import Http404
from .models import Movie, Myrating, MyList
from django.db.models import Q
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.db.models import Case, When
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel


# Create your views here.

def index(request):
    movies = Movie.objects.all()
    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct()
        return render(request, 'recommend/list.html', {'movies': movies})

    return render(request, 'recommend/list.html', {'movies': movies})


def detail(request, movie_id):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404
    movies = get_object_or_404(Movie, id=movie_id)
    movie = Movie.objects.get(id=movie_id)
    
    temp = list(MyList.objects.all().values().filter(movie_id=movie_id,user=request.user))
    if temp:
        update = temp[0]['watch']
    else:
        update = False
    if request.method == "POST":


        if 'watch' in request.POST:
            watch_flag = request.POST['watch']
            if watch_flag == 'on':
                update = True
            else:
                update = False
            if MyList.objects.all().values().filter(movie_id=movie_id,user=request.user):
                MyList.objects.all().values().filter(movie_id=movie_id,user=request.user).update(watch=update)
            else:
                q=MyList(user=request.user,movie=movie,watch=update)
                q.save()
            if update:
                messages.success(request, "Film listeye eklendi!")
            else:
                messages.success(request, "Film listeden kaldırıldı!")



        else:
            rate = request.POST['rating']
            if Myrating.objects.all().values().filter(movie_id=movie_id,user=request.user):
                Myrating.objects.all().values().filter(movie_id=movie_id,user=request.user).update(rating=rate)
            else:
                q=Myrating(user=request.user,movie=movie,rating=rate)
                q.save()

            messages.success(request, "Film oylandı!")

        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    out = list(Myrating.objects.filter(user=request.user.id).values())


    movie_rating = 0
    rate_flag = False
    for each in out:
        if each['movie_id'] == movie_id:
            movie_rating = each['rating']
            rate_flag = True
            break

    context = {'movies': movies,'movie_rating':movie_rating,'rate_flag':rate_flag,'update':update}
    return render(request, 'recommend/detail.html', context)


def watch(request):

    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404

    movies = Movie.objects.filter(mylist__watch=True,mylist__user=request.user)
    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct()
        return render(request, 'recommend/watch.html', {'movies': movies})

    return render(request, 'recommend/watch.html', {'movies': movies})


def recommend(request):

    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404


    movies_table = pd.DataFrame(list(Movie.objects.all().values()))

    # TF-IDF vectorizer objesi oluştur. and, is, the gibi ingilizce kelimeleri temizle.
    tfidf = TfidfVectorizer(stop_words='english')

    # NaN alanları boş string ile değiştir.
    movies_table = movies_table.fillna('')

    print(movies_table['description'])
    print(movies_table['title'])

    # Verilere fitting ve transforming yaparak tfidf matrisini oluştur.
    tfidf_matrix = tfidf.fit_transform(movies_table['description'])

    # tf-idf matrisi çıktısı.
    print(tfidf_matrix.shape)

    # bir takım kelimeleri listele
    print(tfidf.get_feature_names()[200:220])

    # kosinüs benzerliği matrisini oluştur.
    cosine_sim = linear_kernel(tfidf_matrix, tfidf_matrix)

    print(cosine_sim.shape)

    print(cosine_sim[1])

    # reverse mapping yap
    indices = pd.Series(movies_table.index, index=movies_table['title']).drop_duplicates()

    print(indices[:10])

    # benzer filmleri bulma fonksiyonu
    def get_recommendations(title, cosine_sim=cosine_sim):
        # ilgili filmin indexini al
        idx = indices[title]

        # bu filme benzer tüm filmlerin pairwise similarity puanlarını al.
        sim_scores = list(enumerate(cosine_sim[idx]))

        # filmleri benzerliğe göre sırala
        sim_scores = sorted(sim_scores, key=lambda x: x[1], reverse=True)

        # benzer 5 filmi al.
        sim_scores = sim_scores[1:6]

        # filmin indislerini al
        movie_indices = [i[0] for i in sim_scores]

        # benzer filmleri döndür.
        return movies_table['title'].iloc[movie_indices]

    movie_list2 = list(Movie.objects.filter(title__in=get_recommendations("Mandariinid")).values())

    print(movie_list2)

    context = {'movie_list2': movie_list2}

    return render(request, 'recommend/recommend.html', context)


def get_similar(movie_name,rating,corrMatrix):
    similar_ratings = corrMatrix[movie_name]*(rating-2.5)
    similar_ratings = similar_ratings.sort_values(ascending=False)

    return similar_ratings


def recommend2(request):

    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404

    movie_rating=pd.DataFrame(list(Myrating.objects.all().values()))
    userRatings = movie_rating.pivot_table(index=['user_id'],columns=['movie_id'],values='rating')
    userRatings = userRatings.fillna(0,axis=1)
    corrMatrix = userRatings.corr(method='pearson')

    user = pd.DataFrame(list(Myrating.objects.filter(user=request.user).values())).drop(['user_id','id'],axis=1)
    user_filtered = [tuple(x) for x in user.values]
    movie_id_watched = [each[0] for each in user_filtered]

    similar_movies = pd.DataFrame()

    for movie,rating in user_filtered:
        similar_movies = similar_movies.append(get_similar(movie,rating,corrMatrix),ignore_index = True)

    movies_id = list(similar_movies.sum().sort_values(ascending=False).index)
    movies_id_recommend = [each for each in movies_id if each not in movie_id_watched]
    preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(movies_id_recommend)])
    movie_list=list(Movie.objects.filter(id__in = movies_id_recommend).order_by(preserved)[:10])

    context = {'movie_list': movie_list}

    print(movie_list)

    return render(request, 'recommend/recommend2.html', context)



def signUp(request):
    form = UserForm(request.POST or None)

    if form.is_valid():
        user = form.save(commit=False)
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user.set_password(password)
        user.save()
        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("index")

    context = {'form': form}

    return render(request, 'recommend/signUp.html', context)


def Login(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("index")
            else:
                return render(request, 'recommend/login.html', {'error_message': 'Your account disable'})
        else:
            return render(request, 'recommend/login.html', {'error_message': 'Invalid Login'})

    return render(request, 'recommend/login.html')


def Logout(request):
    logout(request)
    return redirect("login")
