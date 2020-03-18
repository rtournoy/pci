# -*- coding: utf-8 -*-

import re
import copy

from gluon.storage import Storage
from gluon.contrib.markdown import WIKI

from datetime import datetime, timedelta, date
from dateutil import parser
from gluon.contrib.appconfig import AppConfig
from lxml import etree

from app_modules.common import *
from app_modules.helper import *
from app_modules import common_forms
from app_modules import common_snippets
from app_modules import common_html
from app_modules import common_tools
from app_modules import common_small_html


myconf = AppConfig(reload=True)

# frequently used constants
csv = False # no export allowed
expClass = None #dict(csv_with_hidden_cols=False, csv=False, html=False, tsv_with_hidden_cols=False, json=False, xml=False)
trgmLimit = myconf.take('config.trgm_limit') or 0.4



######################################################################################################################################################################
# Recommended articles search & list (public)
def recommended_articles():
	response.view='default/gab_list_layout.html'

	myVars = request.vars
	qyKwArr = []
	qyTF = []
	myVars2 = {}
	for myVar in myVars:
		if isinstance(myVars[myVar], list):
			myValue = (myVars[myVar])[1]
		else:
			myValue = myVars[myVar]
		if (myVar == 'qyKeywords'):
			qyKw = myValue
			myVars2[myVar] = myValue
			qyKwArr = qyKw.split(' ')
		elif (myVar == 'qyThemaSelect') and myValue:
			qyTF=[myValue]
			myVars2['qy_'+myValue] = True
		elif (re.match('^qy_', myVar) and myValue=='on' and not('qyThemaSelect' in myVars)):
			qyTF.append(re.sub(r'^qy_', '', myVar))
			myVars2[myVar] = myValue

	filtered = db.executesql('SELECT * FROM search_articles(%s, %s, %s, %s, %s);', placeholders=[qyTF, qyKwArr, 'Recommended', trgmLimit, True], as_dict=True)
	
	totalArticles = len(filtered)
	myRows = []
	for row in filtered:
		r = common_snippets.getRecommArticleRowCard(auth, db, response, Storage(row), withImg=True, withScore=False, withDate=True)
		if r:
			myRows.append(r)
			
	grid = DIV(
				DIV(
					DIV(T('%s articles found')%(totalArticles), _class='pci-nResults'),
					DIV(
						myRows, 
						_class='pci2-articles-list'
					), 
					_class='pci-lastArticles-div'
				), 
			_class='searchRecommendationsDiv')


	searchForm = common_forms.getSearchForm(auth, db, myVars2)
	
	return dict(
				grid=grid, 
				myTitle=getTitle(request, auth, db, '#RecommendedArticlesTitle'),
				myText=getText(request, auth, db, '#RecommendedArticlesText'),
				myHelp=getHelp(request, auth, db, '#RecommendedArticles'),
				shareable=True,
				searchableList = True,
				searchForm = searchForm
			)


######################################################################################################################################################################
def all_recommended_articles():
	response.view='default/myLayout.html'

	allR = db.executesql('SELECT * FROM search_articles(%s, %s, %s, %s, %s);', placeholders=[['.*'], None, 'Recommended', trgmLimit, True], as_dict=True)
	myRows = []
	for row in allR:
		r = common_snippets.getRecommArticleRowCard(auth, db, response, Storage(row), withImg=True, withScore=False, withDate=True)
		if r:
			myRows.append(r)
	n = len(allR)

	grid = DIV(
			DIV(
				DIV(T('%s articles found')%(n), _class='pci-nResults'),
				DIV(
					myRows, 
					_class='pci2-articles-list'
				), 
				_class='pci-lastArticles-div'
			), 
			_class='searchRecommendationsDiv')
	return dict(
				grid=grid, 
				#searchForm=searchForm, 
				myTitle=getTitle(request, auth, db, '#AllRecommendedArticlesTitle'),
				myText=getText(request, auth, db, '#AllRecommendedArticlesText'),
				myHelp=getHelp(request, auth, db, '#AllRecommendedArticles'),
				shareable=True,
			)

######################################################################################################################################################################
# Recommendations of an article (public)
def rec():
	scheme=myconf.take('alerts.scheme')
	host=myconf.take('alerts.host')
	port=myconf.take('alerts.port', cast=lambda v: common_small_html.takePort(v) )

	with_reviews = 'reviews' in request.vars and request.vars['reviews']=='True'
	# with_reviews = True
	with_comments = 'comments' in request.vars and request.vars['comments']=='True'
	# with_comments = True
	printable = 'printable' in request.vars  and request.vars['printable']=='True'
	
	as_pdf = 'asPDF' in request.vars and request.vars['asPDF']=='True'

	# security : Is content avalaible ? 
	if ('articleId' in request.vars):
		articleId = request.vars['articleId']
	elif ('id' in request.vars):
		articleId = request.vars['id']
	else:
		session.flash = T('Unavailable')
		redirect(URL('articles', 'recommended_articles', user_signature=True))
	
	# NOTE: check id is numeric!
	if (not articleId.isdigit()):
		session.flash = T('Unavailable')
		redirect(URL('articles', 'recommended_articles', user_signature=True))
		
	art = db.t_articles[articleId]

	if art == None:
		session.flash = T('Unavailable')
		redirect(URL('articles', 'recommended_articles', user_signature=True))
	# NOTE: security hole possible by articleId injection: Enforced checkings below.
	elif art.status != 'Recommended':
		session.flash = T('Forbidden access')
		redirect(URL('articles', 'recommended_articles', user_signature=True))
	
	if (as_pdf):
		pdfQ = db( (db.t_pdf.recommendation_id == db.t_recommendations.id) & (db.t_recommendations.article_id == art.id) ).select(db.t_pdf.id, db.t_pdf.pdf)
		if len(pdfQ) > 0:
			redirect(URL('default', 'download', args=pdfQ[0]['pdf']))
		else:
			session.flash = T('Unavailable')
			redirect(redirect(request.env.http_referer))


	# Set Page title
	finalRecomm = db( (db.t_recommendations.article_id==art.id) & (db.t_recommendations.recommendation_state=='Recommended') ).select(orderby=db.t_recommendations.id).last()
	if finalRecomm:
		response.title = (finalRecomm.recommendation_title or myconf.take('app.longname'))
	else:
		response.title = myconf.take('app.longname')
	response.title = common_tools.getShortText(response.title, 64)
	

	nbRecomms = db( (db.t_recommendations.article_id==art.id) ).count()
	nbRevs = db( (db.t_recommendations.article_id==art.id) & (db.t_reviews.recommendation_id==db.t_recommendations.id) ).count()
	nbReviews = (nbRevs + (nbRecomms-1))
	
	# Recommendation Header and Metadata
	recommendationHeader = common_snippets.getRecommendationHeaderHtml(auth, db, response, art, finalRecomm, printable)
	recommHeaderHtml = recommendationHeader['headerHtml']
	recommMetadata = recommendationHeader['recommMetadata']

	if len(recommMetadata)>0:
		response.meta = recommMetadata
	
	reviewRounds = None
	if with_reviews:
		# Get review rounds tree
		reviewRounds = DIV(common_snippets.getReviewRoundsHtml(auth, db, response, art.id))

	commentsTreeAndForm = None
	if with_comments:
		# Get user comments list and form
		commentsTreeAndForm = common_snippets.getRecommCommentListAndForm(auth, db, response, session, art.id, with_reviews, request.vars['replyTo'])
	
	
	if printable:
		response.view='default/wrapper_printable.html'
	else:
		response.view='default/wrapper_normal.html'

	viewToRender='default/gab_public_article_recommendation.html'

	return dict(
				withReviews=with_reviews,
				withComments=with_comments,
				toggleReviewsUrl=URL(c='articles', f='rec', vars=dict(articleId=articleId, reviews=not(with_reviews), comments=with_comments), user_signature=True),
				toggleCommentsUrl=URL(c='articles', f='rec', vars=dict(articleId=articleId, reviews=with_reviews, comments=not(with_comments)), user_signature=True),
				printableUrl=URL(c='articles', f='rec', vars=dict(articleId=articleId, reviews=with_reviews, comments=with_comments, printable=True), user_signature=True),
				currentUrl=URL(c='articles', f='rec', vars=dict(articleId=articleId, reviews=with_reviews, comments=with_comments), host=host, scheme=scheme, port=port),
				shareButtons=True,
				nbReviews = nbReviews,
				recommHeaderHtml = recommHeaderHtml,
				reviewRounds = reviewRounds,
				commentsTreeAndForm = commentsTreeAndForm,
				viewToRender=viewToRender
			)

######################################################################################################################################################################
def tracking():
	response.view='default/gab_list_layout.html'

	tracking = myconf.get('config.tracking', default=False)
	if tracking is False:
		session.flash = T('Unavailable')
		redirect(redirect(request.env.http_referer))
	else:
		article_list = DIV(_class='pci2-articles-list') 
		
		query_already_published_articles = db(db.t_articles.already_published==False).select(orderby=~db.t_articles.last_status_change)
		
		for article in query_already_published_articles:
			article_html_card = common_snippets.getArticleTrackcRowCard(auth, db, response, article)
			if article_html_card:
				article_list.append(article_html_card)
		
		resu = dict(
			myHelp=getHelp(request, auth, db, '#Tracking'),
			myTitle=getTitle(request, auth, db, '#TrackingTitle'),
			myText=getText(request, auth, db, '#TrackingText'),
			grid = DIV(
					article_list,
					_class='pci2-flex-center'
				)
		)
		return resu


# (gab) not working ? 
# STRANGE ERROR : local variable 'myContents' referenced before assignment
######################################################################################################################################################################
def pubReviews():
	response.view='default/myLayout.html'

	myContents = DIV()
	tracking = myconf.get('config.tracking', default=False)
	if tracking is False:
		session.flash = T('Unavailable')
		redirect(redirect(request.env.http_referer))
	elif ('articleId' in request.vars):
		articleId = request.vars['articleId']
	elif ('id' in request.vars):
		articleId = request.vars['id']
	else:
		session.flash = T('Unavailable')
		redirect(redirect(request.env.http_referer))
	# NOTE: check id is numeric!
	if (not articleId.isdigit()):
		session.flash = T('Unavailable')
		redirect(redirect(request.env.http_referer))
		
	art = db.t_articles[articleId]
	if art is None:
		session.flash = T('Unavailable')
		redirect(redirect(request.env.http_referer))
	elif art.status != 'Cancelled':
		session.flash = T('Unavailable')
		redirect(redirect(request.env.http_referer))
	else:
		myContents = DIV(reviewsOfCancelled(auth, db, art))
	
	resu = dict(
			myHelp=getHelp(request, auth, db, '#TrackReviews'),
			myTitle=getTitle(request, auth, db, '#TrackReviewsTitle'),
			myText=getText(request, auth, db, '#TrackReviewsText'),
			grid = myContents
		)
	return resu




######################################################################################################################################################################
@cache.action(time_expire=30, cache_model=cache.ram, quick='V')
def last_recomms():
	if 'maxArticles' in request.vars:
		maxArticles = int(request.vars['maxArticles'])
	else:
		maxArticles = 10
	myVars = copy.deepcopy(request.vars)
	myVars['maxArticles'] = (myVars['maxArticles'] or 10)
	myVarsNext = copy.deepcopy(myVars)
	myVarsNext['maxArticles'] = int(myVarsNext['maxArticles'])+10

	queryRecommendedArticles = None
	#if 'qyThemaSelect' in request.vars:
		#thema = request.vars['qyThemaSelect']
		#if thema and len(thema)>0:
			#query = db( 
					#(db.t_articles.status=='Recommended') 
				  #& (db.t_recommendations.article_id==db.t_articles.id) 
				  #& (db.t_recommendations.recommendation_state=='Recommended')
				  #& (db.t_articles.thematics.contains(thema)) 
				#).iterselect(db.t_articles.id, db.t_articles.title, db.t_articles.authors, db.t_articles.article_source, db.t_articles.doi, db.t_articles.picture_rights_ok, db.t_articles.uploaded_picture, db.t_articles.abstract, db.t_articles.upload_timestamp, db.t_articles.user_id, db.t_articles.status, db.t_articles.last_status_change, db.t_articles.thematics, db.t_articles.keywords, db.t_articles.already_published, db.t_articles.i_am_an_author, db.t_articles.is_not_reviewed_elsewhere, db.t_articles.auto_nb_recommendations, limitby=(0, maxArticles), orderby=~db.t_articles.last_status_change)
	if queryRecommendedArticles is None:
		queryRecommendedArticles = db( 
			(db.t_articles.status=='Recommended') 
		  	& (db.t_recommendations.article_id==db.t_articles.id) 
		  	& (db.t_recommendations.recommendation_state=='Recommended')
		).iterselect(
			db.t_articles.id, 
			db.t_articles.title, 
			db.t_articles.authors, 
			db.t_articles.article_source, 
			db.t_articles.doi, 
			db.t_articles.picture_rights_ok, 
			db.t_articles.uploaded_picture, 
			db.t_articles.abstract, 
			db.t_articles.upload_timestamp, 
			db.t_articles.user_id, 
			db.t_articles.status, 
			db.t_articles.last_status_change, 
			db.t_articles.thematics, 
			db.t_articles.keywords, 
			db.t_articles.already_published, 
			db.t_articles.i_am_an_author, 
			db.t_articles.is_not_reviewed_elsewhere, 
			db.t_articles.auto_nb_recommendations, 
			limitby=(0, maxArticles), 
			orderby=~db.t_articles.last_status_change
		)

	recommendedArticlesList = []
	for row in queryRecommendedArticles:
		r = common_snippets.getRecommArticleRowCard(auth, db, response, row, withDate=True)
		if r:
			recommendedArticlesList.append(r)
	
	if len(recommendedArticlesList) == 0:
		return DIV(I(T('Coming soon...')))
	
	if len(recommendedArticlesList) < maxArticles:
		moreState = ' disabled'
	else:
		moreState = ''
	return DIV(
			DIV(
				recommendedArticlesList, 
				_class='pci2-articles-list'
			), 
			DIV(
				A(current.T('More...'), _id='moreLatestBtn',
					_onclick="ajax('%s', ['qyThemaSelect', 'maxArticles'], 'lastRecommendations')"%(URL('articles', 'last_recomms', vars=myVarsNext, user_signature=True)),
					_class='btn btn-default'+moreState, _style='margin-left:8px; margin-bottom:8px;'
				),
				A(current.T('See all recommendations'), _href=URL('articles', 'all_recommended_articles'), _class='btn btn-default', _style='margin-left:32px; margin-bottom:8px;'),
				_style='text-align:center;'
			),
			_class='pci-lastArticles-div',
		)