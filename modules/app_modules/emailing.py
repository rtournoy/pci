# -*- coding: utf-8 -*-

import os
import datetime
import time
from re import sub, match

# from copy import deepcopy
from dateutil.relativedelta import *
import traceback
from pprint import pprint

from gluon import current
from gluon.tools import Auth
from gluon.html import *
from gluon.template import render
from gluon.contrib.markdown import WIKI
from gluon.contrib.appconfig import AppConfig
from gluon.tools import Mail

from gluon.custom_import import track_changes

track_changes(True)
import socket

from uuid import uuid4
from contextlib import closing
import shutil

from app_modules import common_tools
from app_modules import common_small_html
from app_modules import old_common
from app_modules import emailing_tools
from app_modules import emailing_parts
from app_modules import emailing_vars
from app_modules import newsletter
from app_modules import reminders
from app_components import ongoing_recommendation
from app_modules.common_small_html import md_to_html
from app_modules.emailing_vars import getPCiRRinvitationTexts
from app_modules.emailing_vars import getPCiRRScheduledSubmissionsVars


myconf = AppConfig(reload=True)
parallelSubmissionAllowed = myconf.get("config.parallel_submission", default=False)

pciRRactivated = myconf.get("config.registered_reports", default=False)
scheduledSubmissionActivated = myconf.get("config.scheduled_submissions", default=False)

default_review_duration = "Two weeks" if pciRRactivated else "Three weeks"

MAIL_DELAY = 1.5  # in seconds

# common view for all emails
MAIL_HTML_LAYOUT = os.path.join(os.path.dirname(__file__), "../../views/mail", "mail.html")

DEFAULT_DATE_FORMAT = common_tools.getDefaultDateFormat()

######################################################################################################################################################################
# Mailing functions
######################################################################################################################################################################

email_subject_header = emailing_tools.email_subject_header
patch_email_subject = emailing_tools.patch_email_subject
get_review_days = reminders.getReviewDaysFromDuration

######################################################################################################################################################################
# TEST MAIL (or "How to properly create an emailing function")
def send_test_mail(session, auth, db, userId):
    print("send_test_mail")
    # Get common variables :
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    # Set custom variables :
    mail_vars["destAddress"] = db.auth_user[userId]["email"]
    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, userId)
    mail_vars["linkTarget"] = URL(c="default", f="index", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

    # Insert mail in mail_queue :
    hashtag_template = "#TestMail"
    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars)

    # Create report for session flash alerts :
    reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    # Build reports :
    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Send email to the requester (if any)
def send_to_submitter(session, auth, db, articleId, newStatus, response):
    print("send_to_submitter")
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    mail_vars["unconsider_limit_days"] = myconf.get("config.unconsider_limit_days", default=20)
    mail_vars["recomm_limit_days"] = myconf.get("config.recomm_limit_days", default=50)

    article = db.t_articles[articleId]
    if article and article.user_id is not None:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        mail_vars["articleTitle"] = md_to_html(article.title)

        recomm = db((db.t_recommendations.article_id == article.id)).select().last()
        recomm_id = None
        if recomm:
            recomm_id = recomm.id

        recommendation = None
        mail_vars["linkTarget"] = URL(c="user", f="my_articles", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

        # Define template depending on the article status changed
        if article.status == "Pending" and newStatus == "Awaiting consideration":
            if article.parallel_submission:
                hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterParallelPreprintSubmitted", article)
            else:
                mail_vars["parallelText"] = ""
                if parallelSubmissionAllowed:
                    mail_vars["parallelText"] += (
                        """Please note that if you abandon the process with %(appName)s after reviewers have contributed their time toward evaluation and before the end of the evaluation, we will post the reviewers' reports on the %(appName)s website as recognition of their work and in order to enable critical discussion."""
                        % mail_vars
                    )
                hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterPreprintSubmitted", article)

        elif article.status == "Awaiting consideration" and newStatus == "Under consideration":
            if article.parallel_submission:
                hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterParallelPreprintUnderConsideration", article)
            else:
                hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterPreprintUnderConsideration", article)

            if pciRRactivated:
                mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        elif article.status != newStatus and newStatus == "Cancelled":
            mail_vars["parallelText"] = ""
            if parallelSubmissionAllowed and article.parallel_submission:
                mail_vars[
                    "parallelText"
                ] += """If your manuscript was sent to reviewers and evaluated, we will add a link to the reports on our progress log page. This is because you chose the parallel submission option and we do not wish to waste the effort that went into evaluating your work. This provides reviewers a possibility to claim credit for their evaluation work and, in addition to being useful to your team, we hope the reports are useful discussion points for other researchers in the field."""
            hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterCancelledSubmission", article)

        elif article.status != newStatus and newStatus == "Rejected":
            recommendation = old_common.mkFeaturedArticle(auth, db, article, printable=True, scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], to_submitter=True)
            mail_vars["recommTarget"] = URL(
                c="user", f="recommendations", vars=dict(articleId=articleId), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"]
            )

            if recomm:
                mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

            hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterRejectedSubmission", article)

        elif article.status != newStatus and newStatus == "Not considered":
            recommendation = old_common.mkFeaturedArticle(auth, db, article, printable=True, scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], to_submitter=True)
            mail_vars["recommTarget"] = URL(
                c="user", f="recommendations", vars=dict(articleId=articleId), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"]
            )

            hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterNotConsideredSubmission", article)

        elif article.status != newStatus and newStatus == "Awaiting revision":
            recommendation = old_common.mkFeaturedArticle(auth, db, article, printable=True, scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], to_submitter=True)
            mail_vars["recommTarget"] = URL(
                c="user", f="recommendations", vars=dict(articleId=articleId), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"]
            )

            if recomm:
                mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

            hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterAwaitingSubmission", article)

        elif article.status != newStatus and newStatus == "Pre-recommended":
            return  # patience!

        elif article.status != newStatus and newStatus == "Recommended":
            lastRecomm = db((db.t_recommendations.article_id == article.id) & (db.t_recommendations.recommendation_state == "Recommended")).select().last()
            mail_vars["linkTarget"] = URL(c="articles", f="rec", vars=dict(id=articleId), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

            if lastRecomm:
                mail_vars["doiRecomm"] = XML(common_small_html.mkLinkDOI(lastRecomm.recommendation_doi))
                mail_vars["recommVersion"] = lastRecomm.ms_version
                mail_vars["recommsList"] = SPAN(common_small_html.getRecommAndReviewAuthors(auth, db, recomm=lastRecomm, with_reviewers=False, linked=False)).flatten()

                mail_vars["ccAddresses"] = [db.auth_user[lastRecomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, lastRecomm.id)
                mail_vars["recommendationProcess"] = ongoing_recommendation.getRecommendationProcess(auth, db, response, article, True)

            hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterRecommendedPreprint", article)

        elif article.status != newStatus and newStatus == "Recommended-private":
            lastRecomm = db((db.t_recommendations.article_id == article.id) & (db.t_recommendations.recommendation_state == "Recommended")).select().last()

            if lastRecomm:
                mail_vars["doiRecomm"] = XML(common_small_html.mkLinkDOI(lastRecomm.recommendation_doi))
                mail_vars["recommVersion"] = lastRecomm.ms_version
                mail_vars["recommsList"] = SPAN(common_small_html.getRecommAndReviewAuthors(auth, db, recomm=lastRecomm, with_reviewers=False, linked=False)).flatten()

                mail_vars["ccAddresses"] = [db.auth_user[lastRecomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, lastRecomm.id)
                mail_vars["recommendationProcess"] = ongoing_recommendation.getRecommendationProcess(auth, db, response, article, True)

            hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterRecommendedPreprintPrivate", article)

        elif article.status != newStatus:
            mail_vars["tOldStatus"] = current.T(article.status)
            mail_vars["tNewStatus"] = current.T(newStatus)

            hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterPreprintStatusChanged", article)
        else:
            return

        # Fill define template with mail_vars :
        emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm_id, recommendation, articleId)

        reports = emailing_tools.createMailReport(True, "submitter " + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Send email to the requester (if any)
def send_to_submitter_acknowledgement_submission(session, auth, db, articleId):
    print("send_to_submitter_acknowledgement_submission")
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    if article and article.user_id is not None:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        mail_vars["articleTitle"] = md_to_html(article.title)

        hashtag_template = emailing_tools.getCorrectHashtag("#SubmitterAcknowledgementSubmission", article)

        emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, None, None, articleId)


##############################################################################
def send_to_submitter_scheduled_submission_open(auth, db, article):
    mail_vars = emailing_tools.getMailCommonVars()
    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
    mail_vars["destAddress"] = db.auth_user[article.user_id].email
    mail_vars["articleTitle"] = md_to_html(article.title)
    mail_vars["recommenderPerson"] = mk_recommender(auth, db, article)
    mail_vars["linkTarget"] = mk_submitter_my_articles_url(mail_vars)

    mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

    hashtag_template = "#SubmitterScheduledSubmissionOpen"
    sending_date = getScheduledSubmissionDate(article) - db.full_upload_opening_offset

    emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, None, None, article.id, sending_date_forced=sending_date)


def mk_recommender(auth, db, article):
    recomm = db.get_last_recomm(article.id)
    return common_small_html.mkUserWithMail(auth, db, recomm.recommender_id)

######################################################################################################################################################################
# Send email to the recommenders (if any) for postprints
def send_to_recommender_postprint_status_changed(session, auth, db, articleId, newStatus):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    article = db.t_articles[articleId]
    if article:
        mail_vars["linkTarget"] = URL(
            c="recommender", f="my_recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], vars=dict(pressReviews=True)
        )
        for myRecomm in db(db.t_recommendations.article_id == articleId).select(db.t_recommendations.recommender_id, db.t_recommendations.id, distinct=True):
            mail_vars["recommender_id"] = myRecomm["recommender_id"]
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, mail_vars["recommender_id"])
            mail_vars["destAddress"] = db.auth_user[myRecomm.recommender_id]["email"]
            mail_vars["articleAuthors"] = article.authors
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
            mail_vars["tOldStatus"] = current.T(article.status)
            mail_vars["tNewStatus"] = current.T(newStatus)

            # mail_vars["ccAddresses"] = emailing_vars.getCoRecommendersMails(db, myRecomm.id)

            hashtag_template = "#RecommenderPostprintStatusChanged"
            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, myRecomm.id, None, articleId)

            reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Send email to the recommenders (if any)
def send_to_recommender_status_changed(session, auth, db, articleId, newStatus):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    mail_vars["recomm_limit_days"] = myconf.get("config.recomm_limit_days", default=50)

    article = db.t_articles[articleId]
    if article is not None:
        mail_vars["linkTarget"] = URL(
            c="recommender", f="my_recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], vars=dict(pressReviews=article.already_published)
        )

        for recommender in db(db.t_recommendations.article_id == articleId).select(db.t_recommendations.recommender_id, distinct=True):
            recommender_id = recommender.recommender_id

            if not recommender_id:
                continue

            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recommender_id)
            mail_vars["destAddress"] = db.auth_user[recommender_id]["email"]
            mail_vars["articleAuthors"] = article.authors
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleDoi"] = XML(common_small_html.mkSimpleDOI(article.doi))
            mail_vars["tOldStatus"] = current.T(article.status)
            mail_vars["tNewStatus"] = current.T(newStatus)

            myRecomm = db(
                (db.t_recommendations.article_id == articleId) &
                (db.t_recommendations.recommender_id == recommender_id)
            ).select(orderby=db.t_recommendations.id).last()

            authors_reply = None
            if article.status == "Awaiting revision" and newStatus == "Under consideration":
                mail_vars["linkTarget"] = URL(
                    c="recommender", f="recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], vars=dict(articleId=article.id)
                )
                mail_vars["deadline"] = (datetime.date.today() + datetime.timedelta(weeks=1)).strftime(DEFAULT_DATE_FORMAT)

                mail_vars["ccAddresses"] = emailing_vars.getCoRecommendersMails(db, myRecomm.id)

                hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderStatusChangedToUnderConsideration", article)
                authors_reply = emailing_parts.getAuthorsReplyHTML(auth, db, myRecomm.id)

            elif newStatus == "Recommended":
                mail_vars["linkRecomm"] = URL(c="articles", f="rec", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], vars=dict(id=article.id))
                mail_vars["doiRecomm"] = common_small_html.mkLinkDOI(myRecomm.recommendation_doi)
                mail_vars["bccAddresses"] = emailing_vars.getManagersMails(db)

                hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderStatusChangedUnderToRecommended", article)

            elif newStatus == "Recommended-private":
                mail_vars["doiRecomm"] = common_small_html.mkLinkDOI(myRecomm.recommendation_doi)

                hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderStatusChangedUnderToRecommendedPrivate", article)

            else:
                hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderArticleStatusChanged", article)

            # Fill define template with mail_vars :
            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, myRecomm.id, None, articleId, authors_reply=authors_reply)

            reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_recommender_decision_sent_back(session, auth, db, articleId, newStatus):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    article = db.t_articles[articleId]
    if article:
        mail_vars["linkTarget"] = URL(
            c="recommender", f="my_recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], vars=dict(pressReviews=True)
        )
        myRecomm = db(db.t_recommendations.article_id == articleId).select(
                      db.t_recommendations.recommender_id, db.t_recommendations.id,
                      distinct=True,
                      orderby=db.t_recommendations.id,
                      ).last()
        if myRecomm:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, myRecomm.recommender_id)
            mail_vars["destAddress"] = db.auth_user[myRecomm.recommender_id]["email"]
            mail_vars["articleAuthors"] = article.authors
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)

            # mail_vars["ccAddresses"] = emailing_vars.getCoRecommendersMails(db, myRecomm.id)

            hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderDecisionSentBack", article)
            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, myRecomm.id, None, articleId)

            reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)


######################################################################################################################################################################
# Do send email to suggested recommenders for a given NO MORE available article
def send_to_suggested_recommenders_not_needed_anymore(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    article = db.t_articles[articleId]
    if article:
        recomm = db((db.t_recommendations.article_id == article.id)).select().last()
        recomm_id = None
        if recomm:
            recomm_id = recomm.id

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
        mail_vars["articleAuthors"] = mkAuthors(article)

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        # TODO: removing auth.user_id is not the best solution... Should transmit recommender_id
        suggested_recommenders = db(
            (db.t_suggested_recommenders.article_id == articleId)
            & (db.t_suggested_recommenders.suggested_recommender_id != auth.user_id)
            & (db.t_suggested_recommenders.declined == False)
            & (db.t_suggested_recommenders.suggested_recommender_id == db.auth_user.id)
        ).select(db.t_suggested_recommenders.ALL, db.auth_user.ALL)
        for sugg_recommender in suggested_recommenders:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, sugg_recommender["auth_user.id"])
            mail_vars["destAddress"] = db.auth_user[sugg_recommender["auth_user.id"]]["auth_user.email"]

            # TODO: parallel submission
            hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderSuggestionNotNeededAnymore", article)
            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm_id, None, articleId)

            reports = emailing_tools.createMailReport(True, "suggested recommender" + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


def mkAuthors(article):
    return article.authors if not article.anonymous_submission else current.T("[undisclosed]")

def mkUnanonymizedAuthors(article):
    return SPAN(article.authors, (" [this is an anonymous submission]"))


######################################################################################################################################################################
# Do send email to suggested recommenders for a given available article
def send_to_suggested_recommenders(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    article = db.t_articles[articleId]
    if article:

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
        mail_vars["articleAuthors"] = mkAuthors(article)

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

            if article.anonymous_submission:
                mail_vars["articleAuthors"] = mkUnanonymizedAuthors(article)

        recomm = db((db.t_recommendations.article_id == article.id)).select().last()
        recomm_id = None
        if recomm:
            recomm_id = recomm.id

        suggested_recommenders = db.executesql(
            "SELECT DISTINCT au.*, sr.id AS sr_id FROM t_suggested_recommenders AS sr JOIN auth_user AS au ON sr.suggested_recommender_id=au.id WHERE sr.email_sent IS FALSE AND sr.declined IS FALSE AND article_id=%s;",
            placeholders=[article.id],
            as_dict=True,
        )
        for sugg_recommender in suggested_recommenders:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, sugg_recommender["id"])
            mail_vars["destAddress"] = db.auth_user[sugg_recommender["id"]]["email"]
            mail_vars["linkTarget"] = URL(
                c="recommender", f="article_details", vars=dict(articleId=article.id), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"]
            )
            mail_vars["helpurl"] = URL(c="help", f="help_generic", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
            mail_vars["ethicsurl"] = mk_ethicsLink()

            if article.parallel_submission:
                mail_vars["addNote"] = (
                    "<b>Note:</b> The authors have chosen to submit their manuscript elsewhere in parallel. We still believe it is useful to review their work at %(appName)s, and hope you will agree to manage this preprint. If the authors abandon the process at %(appName)s after reviewers have written their reports, we will post the reviewers' reports on the %(appName)s website as recognition of the reviewers' work and in order to enable critical discussion."
                    % mail_vars
                )
            else:
                mail_vars["addNote"] = ""

            declineLinkTarget = URL(
                c="recommender_actions",
                f="decline_new_article_to_recommend",
                vars=dict(articleId=article.id),
                scheme=mail_vars["scheme"],
                host=mail_vars["host"],
                port=mail_vars["port"],
            )

            sugg_recommender_buttons = DIV(
                A(
                    SPAN(
                        current.T("Yes, I would like to handle the evaluation process"),
                        _style="margin: 10px; font-size: 14px; background: #93c54b; font-weight:bold; color: white; padding: 5px 15px; border-radius: 5px; display: block",
                    ),
                    _href=mail_vars["linkTarget"],
                    _style="text-decoration: none; display: block",
                ),
                B(current.T("OR")),
                A(
                    SPAN(
                        current.T("No, I would rather not"),
                        _style="margin: 10px; font-size: 14px; background: #f47c3c; font-weight:bold; color: white; padding: 5px 15px; border-radius: 5px; display: block",
                    ),
                    _href=declineLinkTarget,
                    _style="text-decoration: none; display: block",
                ),
                _style="width: 100%; text-align: center; margin-bottom: 25px;",
            )

            hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderSuggestedArticle", article)

            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm_id, None, articleId, sugg_recommender_buttons=sugg_recommender_buttons)

            delete_reminder_for_submitter(db, "#ReminderSubmitterSuggestedRecommenderNeeded", articleId)

            reports = emailing_tools.createMailReport(True, "suggested recommender" + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Do send email to suggested recommenders for a given available article
def send_to_suggested_recommender(session, auth, db, articleId, suggRecommId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    article = db.t_articles[articleId]
    if article:

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
        mail_vars["articleAuthors"] = mkAuthors(article)

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

            if article.anonymous_submission:
                mail_vars["articleAuthors"] = mkUnanonymizedAuthors(article)

        recomm = db((db.t_recommendations.article_id == article.id)).select().last()
        recomm_id = None
        if recomm:
            recomm_id = recomm.id

        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, suggRecommId)
        mail_vars["destAddress"] = db.auth_user[suggRecommId]["email"]
        mail_vars["linkTarget"] = URL(
            c="recommender", f="article_details", vars=dict(articleId=article.id), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"]
        )
        mail_vars["helpurl"] = URL(c="help", f="help_generic", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
        mail_vars["ethicsurl"] = mk_ethicsLink()

        if article.parallel_submission:
            mail_vars["addNote"] = (
                "<b>Note:</b> The authors have chosen to submit their manuscript elsewhere in parallel. We still believe it is useful to review their work at %(appName)s, and hope you will agree to manage this preprint. If the authors abandon the process at %(appName)s after reviewers have written their reports, we will post the reviewers' reports on the %(appName)s website as recognition of the reviewers' work and in order to enable critical discussion."
                % mail_vars
            )
        else:
            mail_vars["addNote"] = ""

        declineLinkTarget = URL(
            c="recommender_actions",
            f="decline_new_article_to_recommend",
            vars=dict(articleId=article.id),
            scheme=mail_vars["scheme"],
            host=mail_vars["host"],
            port=mail_vars["port"],
        )

        sugg_recommender_buttons = DIV(
            A(
                SPAN(
                    current.T("Yes, I would like to handle the evaluation process"),
                    _style="margin: 10px; font-size: 14px; background: #93c54b; font-weight:bold; color: white; padding: 5px 15px; border-radius: 5px; display: block",
                ),
                _href=mail_vars["linkTarget"],
                _style="text-decoration: none; display: block",
            ),
            B(current.T("OR")),
            A(
                SPAN(
                    current.T("No, I would rather not"),
                    _style="margin: 10px; font-size: 14px; background: #f47c3c; font-weight:bold; color: white; padding: 5px 15px; border-radius: 5px; display: block",
                ),
                _href=declineLinkTarget,
                _style="text-decoration: none; display: block",
            ),
            _style="width: 100%; text-align: center; margin-bottom: 25px;",
        )

        hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderSuggestedArticle", article)

        emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm_id, None, articleId, sugg_recommender_buttons=sugg_recommender_buttons)

        delete_reminder_for_submitter(db, "#ReminderSubmitterSuggestedRecommenderNeeded", articleId)

        reports = emailing_tools.createMailReport(True, "suggested recommender" + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Do send email to recommender when a review is closed
def send_to_recommenders_review_completed(session, auth, db, reviewId):
    print("send_to_recommenders_review_completed")
    mail_vars = emailing_tools.getMailCommonVars()

    reports = []

    rev = db.t_reviews[reviewId]
    recomm = db.t_recommendations[rev.recommendation_id]
    if recomm:
        article = db.t_articles[recomm["article_id"]]
        if article:
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["linkTarget"] = URL(
                c="recommender",
                f="my_recommendations",
                scheme=mail_vars["scheme"],
                host=mail_vars["host"],
                port=mail_vars["port"],
                vars=dict(pressReviews=article.already_published),
            )

            recommender = db.auth_user[recomm.recommender_id]
            if recommender:
                mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
                mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]
                mail_vars["reviewerPerson"] = common_small_html.mkUserWithMail(auth, db, rev.reviewer_id)

                hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderReviewerReviewCompleted", article)

                reviewHTML = emailing_parts.getReviewHTML(auth, db, rev.id)

                emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id, review=reviewHTML)

                reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


# ######################################################################################################################################################################
# # Do send email to recommender when a co correcommender accepted recommendation
# def send_to_recommender_co_recommender_considerated(session, auth, db, pressId):
#     print("send_to_recommender_co_recommender_considerated")
#     mail_vars = emailing_tools.getMailCommonVars()
#     reports = []

#     press = db.t_press_reviews[pressId]
#     recomm = db.t_recommendations[press.recommendation_id]
#     if recomm:
#         article = db.t_articles[recomm["article_id"]]
#         if article:
#             mail_vars["linkTarget"] = URL(
#                 c="recommender",
#                 f="my_recommendations",
#                 scheme=mail_vars["scheme"],
#                 host=mail_vars["host"],
#                 port=mail_vars["port"],
#                 vars=dict(pressReviews=article.already_published),
#             )
#             mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
#             mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]
#             mail_vars["contributorPerson"] = common_small_html.mkUserWithMail(auth, db, press.contributor_id)

#             hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderCoRecommenderConsiderated", article)

#             emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

#             reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

#     emailing_tools.getFlashMessage(session, reports)


# ######################################################################################################################################################################
# def send_to_recommenders_co_recommender_declined(session, auth, db, pressId):
#     print("send_to_recommenders_co_recommender_declined")
#     mail_vars = emailing_tools.getMailCommonVars()
#     reports = []

#     press = db.t_press_reviews[pressId]
#     recomm = db.t_recommendations[press.recommendation_id]
#     if recomm:
#         article = db.t_articles[recomm["article_id"]]
#         if article:
#             mail_vars["articleTitle"] = md_to_html(article.title)
#             mail_vars["linkTarget"] = URL(
#                 c="recommender",
#                 f="my_recommendations",
#                 scheme=mail_vars["scheme"],
#                 host=mail_vars["host"],
#                 port=mail_vars["port"],
#                 vars=dict(pressReviews=article.already_published),
#             )
#             mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
#             mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]
#             mail_vars["contributorPerson"] = common_small_html.mkUserWithMail(auth, db, press.contributor_id)

#             hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderCoRecommenderDeclined", article)

#             emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

#             reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

#     emailing_tools.getFlashMessage(session, reports)


# ######################################################################################################################################################################
# def send_to_recommenders_co_recommender_agreement(session, auth, db, pressId):
#     print("send_to_recommenders_co_recommender_agreement")
#     mail_vars = emailing_tools.getMailCommonVars()
#     reports = []

#     press = db.t_press_reviews[pressId]
#     recomm = db.t_recommendations[press.recommendation_id]
#     if recomm:
#         article = db.t_articles[recomm["article_id"]]
#         if article:
#             mail_vars["articleTitle"] = md_to_html(article.title)
#             mail_vars["linkTarget"] = URL(
#                 c="recommender",
#                 f="my_recommendations",
#                 scheme=mail_vars["scheme"],
#                 host=mail_vars["host"],
#                 port=mail_vars["port"],
#                 vars=dict(pressReviews=article.already_published),
#             )
#             mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
#             mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]
#             mail_vars["contributorPerson"] = common_small_html.mkUserWithMail(auth, db, press.contributor_id)

#             hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderCoRecommenderAgreement", article)

#             emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

#             reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

#     emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Do send email to recommender when a review is accepted for consideration
def send_to_recommenders_review_considered(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    rev = db.t_reviews[reviewId]
    recomm = db.t_recommendations[rev.recommendation_id]
    if recomm:
        article = db.t_articles[recomm["article_id"]]
        if article:
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
            mail_vars["articleAuthors"] = mkAuthors(article)
            mail_vars["linkTarget"] = URL(
                c="recommender",
                f="my_recommendations",
                scheme=mail_vars["scheme"],
                host=mail_vars["host"],
                port=mail_vars["port"],
                vars=dict(pressReviews=article.already_published),
            )
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
            mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]
            mail_vars["reviewerPerson"] = common_small_html.mkUserWithMail(auth, db, rev.reviewer_id)
            mail_vars["expectedDuration"] = datetime.timedelta(days=get_review_days(rev.review_duration))
            mail_vars["dueTime"] = str((datetime.datetime.now() + mail_vars["expectedDuration"]).strftime(DEFAULT_DATE_FORMAT))

            if pciRRactivated:
                mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

            hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderReviewConsidered", article)

            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

            reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_recommenders_review_declined(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    rev = db.t_reviews[reviewId]
    recomm = db.t_recommendations[rev.recommendation_id]
    if recomm:
        article = db.t_articles[recomm["article_id"]]
        if article:
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
            mail_vars["articleAuthors"] = mkAuthors(article)
            mail_vars["linkTarget"] = URL(
                c="recommender",
                f="my_recommendations",
                scheme=mail_vars["scheme"],
                host=mail_vars["host"],
                port=mail_vars["port"],
                vars=dict(pressReviews=article.already_published),
            )
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
            recommender = db.auth_user[recomm.recommender_id]
            if recommender is not None:
                mail_vars["destAddress"] = recommender["email"]
                mail_vars["reviewerPerson"] = common_small_html.mkUserWithMail(auth, db, rev.reviewer_id)

                hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderReviewDeclined", article)

                emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

            reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_recommenders_pending_review_request(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    rev = db.t_reviews[reviewId]
    recomm = db.t_recommendations[rev.recommendation_id]
    if recomm:
        article = db.t_articles[recomm["article_id"]]
        if article:
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
            mail_vars["articleAuthors"] = mkAuthors(article)
            mail_vars["linkTarget"] = URL(
                c="recommender", f="recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], vars=dict(articleId=article.id),
            )
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
            mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]
            mail_vars["reviewerPerson"] = common_small_html.mkUserWithMail(auth, db, rev.reviewer_id)

            hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderPendingReviewRequest", article)

            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

            reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Do send email to recommender when a review is re-opened
def send_to_reviewer_review_reopened(session, auth, db, reviewId, newForm):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    rev = db.t_reviews[reviewId]
    recomm = db.t_recommendations[rev.recommendation_id]
    if recomm:
        article = db.t_articles[recomm["article_id"]]
        if article:
            mail_vars["linkTarget"] = URL(c="user", f="my_reviews", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
            mail_vars["articleTitle"] = B(md_to_html(article.title))
            mail_vars["articleAuthors"] = mkAuthors(article)

            reviewer = db.auth_user[rev.reviewer_id]
            if reviewer:
                mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, recomm.recommender_id) or ""
                mail_vars["destPerson"] = common_small_html.mkUser(auth, db, rev.reviewer_id)
                mail_vars["destAddress"] = db.auth_user[rev.reviewer_id]["email"]

                mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

                hashtag_template = emailing_tools.getCorrectHashtag("#ReviewerReviewReopened", article)

                emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_reviewers_article_cancellation(session, auth, db, articleId, newStatus):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    article = db.t_articles[articleId]
    if article:
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
        mail_vars["articleAuthors"] = mkAuthors(article)
        mail_vars["linkTarget"] = URL(c="user", f="my_reviews", vars=dict(pendingOnly=True), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        lastRecomm = db.get_last_recomm(article.id)
        if lastRecomm:
            reviewers = db((db.t_reviews.recommendation_id == lastRecomm.id) & (db.t_reviews.review_state in ("Awaiting response", "Awaiting review", "Review completed"))).select()
            for rev in reviewers:
                if rev is not None and rev.reviewer_id is not None:
                    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, rev.reviewer_id)
                    mail_vars["destAddress"] = db.auth_user[rev.reviewer_id]["email"]
                    mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, lastRecomm.recommender_id)

                    mail_vars["ccAddresses"] = [db.auth_user[lastRecomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, lastRecomm.id)

                    hashtag_template = emailing_tools.getCorrectHashtag("#ReviewersArticleCancellation", article)

                    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, lastRecomm.id, None, article.id)

                    reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)
        else:
            print("send_to_reviewers_article_cancellation: Recommendation not found")
    else:
        print("send_to_reviewers_article_cancellation: Article not found")

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_reviewer_review_request_accepted(session, auth, db, reviewId, newForm):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    rev = db.t_reviews[reviewId]
    if rev:
        recomm = db.t_recommendations[rev.recommendation_id]
        if recomm:
            article = db.t_articles[recomm["article_id"]]
            if article:
                mail_vars["articleTitle"] = md_to_html(article.title)
                mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
                mail_vars["articleAuthors"] = mkAuthors(article)
                mail_vars["linkTarget"] = URL(c="user", f="my_reviews", vars=dict(pendingOnly=False), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

                reviewer = db.auth_user[rev.reviewer_id]
                if reviewer:
                    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, rev.reviewer_id)
                    mail_vars["destAddress"] = reviewer["email"]

                    mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, recomm.recommender_id) or ""
                    mail_vars["expectedDuration"] = datetime.timedelta(days=get_review_days(rev.review_duration))
                    mail_vars["dueTime"] = str((datetime.datetime.now() + mail_vars["expectedDuration"]).strftime(DEFAULT_DATE_FORMAT))
                    
                    mail_vars["reviewDuration"] = (rev.review_duration).lower()
                    
                    hashtag_template = emailing_tools.getCorrectHashtag("#ReviewerReviewRequestAccepted", article)

                    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                    reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_reviewer_review_request_declined(session, auth, db, reviewId, newForm):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    rev = db.t_reviews[reviewId]
    if rev:
        recomm = db.t_recommendations[rev.recommendation_id]
        if recomm:
            article = db.t_articles[recomm["article_id"]]
            if article:
                mail_vars["articleTitle"] = md_to_html(article.title)
                mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
                mail_vars["articleAuthors"] = mkAuthors(article)
                mail_vars["linkTarget"] = URL(c="user", f="my_reviews", vars=dict(pendingOnly=False), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

                reviewer = db.auth_user[rev.reviewer_id]
                if reviewer:
                    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, rev.reviewer_id)
                    mail_vars["destAddress"] = reviewer["email"]

                    mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, recomm.recommender_id) or ""
                    mail_vars["expectedDuration"] = datetime.timedelta(days=get_review_days(rev.review_duration))
                    mail_vars["dueTime"] = str((datetime.datetime.now() + mail_vars["expectedDuration"]).strftime(DEFAULT_DATE_FORMAT))

                    hashtag_template = emailing_tools.getCorrectHashtag("#ReviewerReviewRequestDeclined", article)

                    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                    reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_thank_reviewer_acceptation(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    rev = db.t_reviews[reviewId]
    if rev:
        recomm = db.t_recommendations[rev.recommendation_id]
        if recomm:
            article = db.t_articles[recomm["article_id"]]
            if article:
                mail_vars["articleTitle"] = md_to_html(article.title)
                mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
                mail_vars["articleAuthors"] = mkAuthors(article)
                mail_vars["linkTarget"] = URL(c="user", f="my_reviews", vars=dict(pendingOnly=False), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

                if pciRRactivated:
                    mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

                reviewer = db.auth_user[rev.reviewer_id]
                if reviewer:
                    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, rev.reviewer_id)
                    mail_vars["destAddress"] = reviewer["email"]

                    mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, recomm.recommender_id) or ""
                    mail_vars["expectedDuration"] = datetime.timedelta(days=get_review_days(rev.review_duration))
                    mail_vars["dueTime"] = str((datetime.datetime.now() + mail_vars["expectedDuration"]).strftime(DEFAULT_DATE_FORMAT))
                    mail_vars["reviewDuration"] = (rev.review_duration).lower()

                    mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

                    hashtag_template = emailing_tools.getCorrectHashtag("#ReviewerThankForReviewAcceptation", article)

                    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                    reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_thank_reviewer_done(session, auth, db, reviewId, newForm):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    rev = db.t_reviews[reviewId]
    if rev:
        recomm = db.t_recommendations[rev.recommendation_id]
        if recomm:
            article = db.t_articles[recomm["article_id"]]
            if article:
                mail_vars["articleTitle"] = md_to_html(article.title)
                mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
                mail_vars["articleAuthors"] = mkAuthors(article)
                mail_vars["linkTarget"] = URL(c="user", f="my_reviews", vars=dict(pendingOnly=False), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

                mail_vars["parallelText"] = ""
                if parallelSubmissionAllowed:
                    mail_vars[
                        "parallelText"
                    ] += """Note that if the authors abandon the process at %(appLongName)s after reviewers have written their reports, we will post the reviewers' reports on the %(appLongName)s website as recognition of their work and in order to enable critical discussion.""" % mail_vars
                    if article.parallel_submission:
                        mail_vars[
                            "parallelText"
                        ] += """Note: The authors have chosen to submit their manuscript elsewhere in parallel. We still believe it is useful to review their work at %(appLongName)s, and hope you will agree to review this preprint.""" % mail_vars

                reviewer = db.auth_user[rev.reviewer_id]
                if reviewer:
                    mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, recomm.recommender_id) or ""
                    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, rev.reviewer_id)
                    mail_vars["destAddress"] = reviewer["email"]

                    hashtag_template = emailing_tools.getCorrectHashtag("#ReviewerThankForReviewDone", article)

                    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                    reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_admin_2_reviews_under_consideration(session, auth, db, reviewId, manual_insert=False):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db((db.t_articles.id == recomm.article_id)).select().last()

    count_reviews_under_consideration = 0
    if recomm:
        count_reviews_under_consideration = db(
            (db.t_reviews.recommendation_id == recomm.id) & ((db.t_reviews.review_state == "Awaiting review") | (db.t_reviews.review_state == "Review completed"))
        ).count()

    if manual_insert == True:
        count_reviews_under_consideration = count_reviews_under_consideration - 1

    if recomm and article and count_reviews_under_consideration == 1:
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = article.authors
        mail_vars["recommenderPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["linkTarget"] = URL(c="manager", f="recommendations", vars=dict(articleId=article.id), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

        hashtag_template = emailing_tools.getCorrectHashtag("#AdminTwoReviewersIn", article)

        admins = db((db.auth_user.id == db.auth_membership.user_id) & (db.auth_membership.group_id == db.auth_group.id) & (db.auth_group.role == "administrator")).select(
            db.auth_user.ALL
        )

        for admin in admins:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, admin.id)
            mail_vars["destAddress"] = admin.email

            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)


######################################################################################################################################################################
def send_to_admin_all_reviews_completed(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db((db.t_articles.id == recomm.article_id)).select().last()

    count_reviews_completed = 0
    count_reviews_under_consideration = 0
    if recomm:
        count_reviews_completed = db((db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Review completed")).count()
        count_reviews_under_consideration = db((db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Awaiting review")).count()

    if recomm and article and count_reviews_completed >= 1 and count_reviews_under_consideration == 1:

        delete_reminder_for_recommender(db, "#ReminderRecommender2ReviewsReceivedCouldMakeDecision", recomm.id)

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = article.authors
        mail_vars["recommenderPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["linkTarget"] = URL(c="manager", f="recommendations", vars=dict(articleId=article.id), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

        hashtag_template = emailing_tools.getCorrectHashtag("#AdminAllReviewsCompleted", article)

        admins = db((db.auth_user.id == db.auth_membership.user_id) & (db.auth_membership.group_id == db.auth_group.id) & (db.auth_group.role == "administrator")).select(
            db.auth_user.ALL
        )

        for admin in admins:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, admin.id)
            mail_vars["destAddress"] = admin.email

            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)


######################################################################################################################################################################
def send_admin_new_user(session, auth, db, userId):
    print("send_admin_new_user")
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    admins = db((db.auth_user.id == db.auth_membership.user_id) & (db.auth_membership.group_id == db.auth_group.id) & (db.auth_group.role == "administrator")).select(
        db.auth_user.ALL
    )
    dest = []

    user = db.auth_user[userId]
    if user:
        mail_vars["userTxt"] = common_small_html.mkUser(auth, db, userId)
        mail_vars["userMail"] = user.email

        for admin in admins:
            mail_vars["destAddress"] = admin.email

            hashtag_template = "#AdminNewUser"
            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars)

    reports = emailing_tools.createMailReport(True, "administrators", reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_new_user(session, auth, db, userId):
    print("send_new_user")
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    # get thematics and alerts
    user = db.auth_user[userId]
    if type(user.thematics) is list:
        thema = user.thematics
    else:
        thema = [user.thematics]
    if type(user.alerts) is list:
        alerts = user.alerts
    else:
        if user.alerts:
            alerts = [user.alerts]
        else:
            alerts = ["[no alerts]"]

    if user:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, userId)
        mail_vars["destAddress"] = db.auth_user[userId]["email"]
        mail_vars["baseurl"] = URL(c="about", f="about", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
        mail_vars["infourl"] = URL(c="help", f="help_generic", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
        mail_vars["recommurl"] = URL(c="about", f="recommenders", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
        mail_vars["thematics"] = ", ".join(thema)
        mail_vars["days"] = ", ".join(alerts)

        if parallelSubmissionAllowed:
            hashtag_template = "#NewUserParallelSubmissionAllowed"
        else:
            hashtag_template = "#NewUser"

        emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars)

        reports = emailing_tools.createMailReport(True, "new user " + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_new_membreship(session, auth, db, membershipId):
    print("send_new_membreship")
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    user = db.auth_user[db.auth_membership[membershipId].user_id]
    group = db.auth_group[db.auth_membership[membershipId].group_id]
    if user and group:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, user.id)
        mail_vars["destAddress"] = db.auth_user[user.id]["email"]

        if group.role == "recommender":
            mail_vars["days"] = ", ".join(user.alerts)
            mail_vars["baseurl"] = URL(c="default", f="index", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
            mail_vars["helpurl"] = URL(c="help", f="help_generic", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
            mail_vars["ethicsurl"] = mk_ethicsLink()

            mail_vars["bccAddresses"] = emailing_vars.getManagersMails(db)

            hashtag_template = "#NewMembreshipRecommender"
            new_role_report = "new recommender "

        elif group.role == "manager":
            mail_vars["bccAddresses"] = emailing_vars.getAdminsMails(db)

            hashtag_template = "#NewMembreshipManager"
            new_role_report = "new manager "

        else:
            return

        emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars)

        reports = emailing_tools.createMailReport(True, new_role_report + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_managers(session, auth, db, articleId, newStatus):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    article = db.t_articles[articleId]
    if article:
        recomm = db((db.t_recommendations.article_id == articleId)).select(orderby=db.t_recommendations.id).last()
        recomm_id = None
        if recomm:
            recomm_id = recomm.id

        recommendation = None

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = article.authors
        mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)

        if article.user_id:
            mail_vars["submitterPerson"] = common_small_html.mkUser(auth, db, article.user_id)  # submitter
        else:
            mail_vars["submitterPerson"] = "?"

        if newStatus == "Pending":
            mail_vars["linkTarget"] = URL(c="manager", f="pending_articles", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

            hashtag_template = emailing_tools.getCorrectHashtag("#ManagersPreprintSubmission", article)

        elif newStatus.startswith("Pre-"):
            if recomm is not None:
                mail_vars["recommenderPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id) or ""  # recommender
            else:
                mail_vars["recommenderPerson"] = "?"
            mail_vars["linkTarget"] = URL(c="manager", f="pending_articles", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

            recommendation = old_common.mkFeaturedArticle(auth, db, article, printable=True, scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
            hashtag_template = emailing_tools.getCorrectHashtag("#ManagersRecommendationOrDecision", article)

        elif newStatus == "Under consideration":
            recomm = db((db.t_recommendations.article_id == articleId)).select(orderby=db.t_recommendations.id).last()
            if recomm is not None:
                mail_vars["recommenderPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id) or ""  # recommender
            else:
                mail_vars["recommenderPerson"] = "?"

            mail_vars["linkTarget"] = URL(c="manager", f="ongoing_articles", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
            recommendation = old_common.mkFeaturedArticle(auth, db, article, printable=True, scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

            if article.status == "Awaiting revision":
                hashtag_template = emailing_tools.getCorrectHashtag("#AdminArticleResubmited", article)
            else:
                hashtag_template = emailing_tools.getCorrectHashtag("#ManagersArticleConsideredForRecommendation", article)

        elif newStatus == "Cancelled":
            mail_vars["linkTarget"] = URL(c="manager", f="completed_articles", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

            hashtag_template = emailing_tools.getCorrectHashtag("#ManagersArticleCancelled", article)

        else:
            mail_vars["linkTarget"] = URL(c="manager", f="all_articles", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
            mail_vars["tOldStatus"] = current.T(article.status)
            mail_vars["tNewStatus"] = current.T(newStatus)

            hashtag_template = emailing_tools.getCorrectHashtag("#ManagersArticleStatusChanged", article)

        for_admins = [
            "#AdminArticleResubmited",
            "#ManagersArticleConsideredForRecommendation",
            "#ManagersArticleStatusChanged",
        ]
        if hashtag_template in listCorrectHashtags(for_admins, article):
            dest_emails = emailing_vars.getAdminsMails(db)
            dest_role = "admin"
        else:
            dest_emails = emailing_vars.getManagersMails(db)
            dest_role = "manager"

        for email in dest_emails:
            mail_vars["destAddress"] = email
            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm_id, recommendation, article.id)
            reports = emailing_tools.createMailReport(True, dest_role + " " + (email or ""), reports)


    emailing_tools.getFlashMessage(session, reports)


def listCorrectHashtags(hashtags, article):
    return [ emailing_tools.getCorrectHashtag(hashtag, article) for hashtag in hashtags ]


######################################################################################################################################################################
def send_to_thank_recommender_postprint(session, auth, db, recommId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    recomm = db.t_recommendations[recommId]
    if recomm:
        article = db.t_articles[recomm.article_id]
        if article:
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleAuthors"] = article.authors
            mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
            mail_vars["linkTarget"] = URL(
                c="recommender",
                f="my_recommendations",
                scheme=mail_vars["scheme"],
                host=mail_vars["host"],
                port=mail_vars["port"],
                vars=dict(pressReviews=article.already_published),
            )

            recommender = db.auth_user[recomm.recommender_id]
            if recommender:
                # recommender = common_small_html.mkUser(auth, db, recomm.recommender_id)
                mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
                mail_vars["destAddress"] = recommender["email"]

                hashtag_template = "#RecommenderThankForPostprint"
                emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_thank_recommender_preprint(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    if articleId:
        article = db.t_articles[articleId]
        if article:
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleAuthors"] = article.authors
            mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
            mail_vars["linkTarget"] = URL(
                c="recommender", f="my_recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], vars=dict(pressReviews=False)
            )

            if pciRRactivated:
                mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

            recomm = db(db.t_recommendations.article_id == articleId).select(orderby=db.t_recommendations.id).last()
            if recomm:
                recommender = db.auth_user[recomm.recommender_id]
                if recommender:
                    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recommender.id)
                    mail_vars["destAddress"] = recommender["email"]
                    mail_vars["reviewDuration"] = default_review_duration.lower()

                    if article.parallel_submission:

                        hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderThankForPreprintParallelSubmission", article)
                    else:

                        hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderThankForPreprint", article)

                    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                    reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_delete_one_corecommender(session, auth, db, contribId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    if contribId:
        contrib = db.t_press_reviews[contribId]
        if contrib:
            recomm = db.t_recommendations[contrib.recommendation_id]
            if recomm:
                article = db.t_articles[recomm.article_id]
                if article:
                    mail_vars["articleTitle"] = md_to_html(article.title)
                    mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
                    mail_vars["articleAuthors"] = mkAuthors(article)
                    mail_vars["articlePrePost"] = "postprint" if article.already_published else "preprint"
                    mail_vars["linkTarget"] = URL(c="recommender", f="my_co_recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
                    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, contrib.contributor_id)
                    mail_vars["destAddress"] = db.auth_user[contrib.contributor_id]["email"]
                    mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, recomm.recommender_id) or ""
                    mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]]
                    mail_vars["bccAddresses"] = emailing_vars.getManagersMails(db)

                    hashtag_template = emailing_tools.getCorrectHashtag("#CoRecommenderRemovedFromArticle", article)

                    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                    reports = emailing_tools.createMailReport(True, "contributor " + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_one_corecommender(session, auth, db, contribId):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    if contribId:
        contrib = db.t_press_reviews[contribId]
        if contrib:
            recomm = db.t_recommendations[contrib.recommendation_id]
            if recomm:
                article = db.t_articles[recomm.article_id]
                if article:
                    mail_vars["articleTitle"] = md_to_html(article.title)
                    mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
                    mail_vars["articleAuthors"] = mkAuthors(article)
                    mail_vars["articlePrePost"] = "postprint" if article.already_published else "preprint"
                    mail_vars["linkTarget"] = URL(c="recommender", f="my_co_recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
                    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, contrib.contributor_id)
                    mail_vars["destAddress"] = db.auth_user[contrib.contributor_id]["email"]
                    mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, recomm.recommender_id) or ""
                    mail_vars["ethicsLink"] = mk_ethicsLink()

                    if article.status in ("Under consideration", "Pre-recommended", "Pre-recommended-private"):
                        mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]]
                        mail_vars["bccAddresses"] = emailing_vars.getManagersMails(db)

                        if article.already_published:
                            hashtag_template = emailing_tools.getCorrectHashtag("#CoRecommenderAddedOnArticleAlreadyPublished", article)
                        else:
                            hashtag_template = emailing_tools.getCorrectHashtag("#CoRecommenderAddedOnArticle", article)

                        emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                        reports = emailing_tools.createMailReport(True, "contributor " + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_corecommenders(session, auth, db, articleId, newStatus):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    article = db.t_articles[articleId]
    recomm = db(db.t_recommendations.article_id == articleId).select(orderby=db.t_recommendations.id).last()
    if recomm:
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleDoi"] = common_small_html.mkDOI(article.doi)
        mail_vars["articleAuthors"] = mkAuthors(article)
        mail_vars["articlePrePost"] = "postprint" if article.already_published else "preprint"
        mail_vars["tOldStatus"] = current.T(article.status)
        mail_vars["tNewStatus"] = current.T(newStatus)
        mail_vars["linkTarget"] = URL(c="recommender", f="my_co_recommendations", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
        mail_vars["recommenderPerson"] = common_small_html.mkUserWithMail(auth, db, recomm.recommender_id) or ""

        contribs = db(db.t_press_reviews.recommendation_id == recomm.id).select()
        for contrib in contribs:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, contrib.contributor_id)
            dest = db.auth_user[contrib.contributor_id]
            if dest:
                mail_vars["destAddress"] = dest["email"]
            else:
                mail_vars["destAddress"] = ""

            if newStatus == "Recommended":
                mail_vars["recommDOI"] = common_small_html.mkLinkDOI(recomm.recommendation_doi)
                mail_vars["linkRecomm"] = URL(c="articles", f="rec", vars=dict(id=article.id), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
                hashtag_template = emailing_tools.getCorrectHashtag("#CoRecommendersArticleRecommended", article)
            elif newStatus == "Recommended-private":
                mail_vars["recommDOI"] = common_small_html.mkLinkDOI(recomm.recommendation_doi)
                hashtag_template = emailing_tools.getCorrectHashtag("#CoRecommendersArticleRecommendedPrivate", article)
            else:
                if newStatus == "Cancelled":
                    mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]]

                hashtag_template = emailing_tools.getCorrectHashtag("#CoRecommendersArticleStatusChanged", article)

            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

            reports = emailing_tools.createMailReport(True, "contributor " + mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_decision_to_reviewers(session, auth, db, articleId, newStatus):
    print("send_decision_to_reviewers")
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    recomm = db(db.t_recommendations.article_id == articleId).select(orderby=db.t_recommendations.id).last()
    if recomm:
        article = db.t_articles[recomm["article_id"]]
        if article:
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleStatus"] = current.T(newStatus)
            mail_vars["linkTarget"] = URL(c="user", f="my_reviews", vars=dict(pendingOnly=False), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
            mail_vars["myRefArticle"] = common_small_html.mkArticleCitation(auth, db, recomm)
            mail_vars["myRefRecomm"] = common_small_html.mkRecommCitation(auth, db, recomm)

            if newStatus == "Recommended":
                reviewers = db(
                    (db.auth_user.id == db.t_reviews.reviewer_id)
                    & (db.t_reviews.recommendation_id == db.t_recommendations.id)
                    & (db.t_recommendations.article_id == article.id)
                    & (db.t_reviews.review_state == "Review completed")
                ).select(db.t_reviews.id, db.auth_user.ALL, distinct=db.auth_user.email)
            else:
                reviewers = db(
                    (db.auth_user.id == db.t_reviews.reviewer_id) & (db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Review completed")
                ).select(db.t_reviews.id, db.auth_user.ALL, distinct=db.auth_user.email)

            for rev in reviewers:
                mail_vars["destPerson"] = common_small_html.mkUser(auth, db, rev.auth_user.id)
                mail_vars["destAddress"] = rev.auth_user.email

                if newStatus == "Recommended":
                    mail_vars["recommDOI"] = common_small_html.mkLinkDOI(recomm.recommendation_doi)
                    mail_vars["linkRecomm"] = URL(c="articles", f="rec", vars=dict(id=article.id), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
                    hashtag_template = emailing_tools.getCorrectHashtag("#ReviewersArticleRecommended", article)
                elif newStatus == "Recommended-private":
                    mail_vars["recommDOI"] = common_small_html.mkLinkDOI(recomm.recommendation_doi)
                    hashtag_template = emailing_tools.getCorrectHashtag("#ReviewersArticleRecommendedPrivate", article)
                else:
                    hashtag_template = emailing_tools.getCorrectHashtag("#ReviewersArticleStatusChanged", article)

                mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

                emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)

                reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Mail for Scheduled submission
##########################c############################################################################################################################################
def send_to_reviewers_preprint_submitted(session, auth, db, articleId):
    article = db.t_articles[articleId]
    finalRecomm = db(db.t_recommendations.article_id == articleId).select().last()

    if article and finalRecomm:

        reviews = db((db.t_reviews.recommendation_id == finalRecomm.id) & (db.t_reviews.review_state == "Awaiting review")).select()
        
        mail_vars = emailing_tools.getMailCommonVars()

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleDoi"] = article.doi

        mail_vars["sender"] = mkSender(auth, db, finalRecomm)
        mail_vars["recommenderPerson"] = common_small_html.mkUser(auth, db, finalRecomm.recommender_id)

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))
            mail_vars.update(getPCiRRinvitationTexts(article))

        for review in reviews:
            # Get common variables :
            reports = []

            # Set custom variables :
            mail_vars["destAddress"] = db.auth_user[review.reviewer_id]["email"]
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, review.reviewer_id)
            mail_vars["linkTarget"] = URL(c="default", f="index", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

            # Insert mail in mail_queue :
            hashtag_template = emailing_tools.getCorrectHashtag("#ReviewerFullPreprint", article, force_scheduled=True)
            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, finalRecomm.id, None, article.id)

            # Create report for session flash alerts :
            reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

            # Build reports :
            emailing_tools.getFlashMessage(session, reports)


def mkSender(auth, db, recomm):
    if auth.user_id == recomm.recommender_id:
        sender = common_small_html.mkUser(auth, db, recomm.recommender_id).flatten()
    else:
        sender = "The Managing Board of " + myconf.get("app.longname") + " on behalf of " + common_small_html.mkUser(auth, db, recomm.recommender_id).flatten()

    return sender

######################################################################################################################################################################
def send_to_recommender_preprint_submitted(session, auth, db, articleId):
    article = db.t_articles[articleId]
    finalRecomm = db(db.t_recommendations.article_id == articleId).select().last()

    if article and finalRecomm:
        # Get common variables :
        mail_vars = emailing_tools.getMailCommonVars()
        reports = []

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleDoi"] = article.doi
        mail_vars["articleAuthors"] = mkAuthors(article)

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))
            mail_vars.update(getPCiRRinvitationTexts(article))

        # Set custom variables :
        mail_vars["destAddress"] = db.auth_user[finalRecomm.recommender_id]["email"]
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, finalRecomm.recommender_id)
        mail_vars["linkTarget"] = URL(c="default", f="index", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

        # Insert mail in mail_queue :
        hashtag_template = "#RecommenderPreprintSubmittedScheduledSubmission"
        emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, finalRecomm.id, None, article.id)

        # Create report for session flash alerts :
        reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

        # Build reports :
        emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
# Mail with templates
######################################################################################################################################################################
def send_reviewer_invitation(session, auth, db, reviewId, replyto_addresses, cc_addresses, hashtag_template, subject, message, reset_password_key=None, linkTarget=None, declineLinkTarget=None, new_round=False, new_stage=False):
    mail_vars = emailing_tools.getMailCommonVars()
    reg_user_reminder_template = None
    new_user_reminder_template = None

    reports = []

    review = db.t_reviews[reviewId]
    if review:
        recomm = db.t_recommendations[review.recommendation_id]
        article = db.t_articles[recomm.article_id]
        if recomm:
            rev = db.auth_user[review["reviewer_id"]]
            if rev:
                mail_vars["destPerson"] = common_small_html.mkUser(auth, db, review.reviewer_id)
                mail_vars["destAddress"] = rev["email"]
                mail_vars["reviewDuration"] = (review.review_duration).lower()

                message = emailing_tools.replaceMailVars(message, mail_vars)
                content = DIV(WIKI(message, safe_mode=False))

                reviewer_invitation_buttons = None
                button_style = "margin: 10px; font-size: 14px; font-weight:bold; color: white; padding: 5px 15px; border-radius: 5px; display: block;"

                if reset_password_key:
                    if linkTarget:
                        link = URL(
                            a=None,
                            c="default",
                            f="user",
                            args="reset_password",
                            vars=dict(key=reset_password_key, _next=linkTarget),
                            scheme=mail_vars["scheme"],
                            host=mail_vars["host"],
                            port=mail_vars["port"],
                        )
                    else:
                        link = URL(
                            a=None,
                            c="default",
                            f="user",
                            args="reset_password",
                            vars=dict(key=reset_password_key),
                            scheme=mail_vars["scheme"],
                            host=mail_vars["host"],
                            port=mail_vars["port"],
                        )

                    reviewer_invitation_buttons = DIV(
                        P(B(current.T("TO ACCEPT OR DECLINE CLICK ON ONE OF THE FOLLOWING BUTTONS:"))),
                        DIV(
                            A(
                                SPAN(
                                    current.T("ACCEPT"),
                                    _style=button_style + "background: #93c54b",
                                ),
                                _href=link,
                                _style="text-decoration: none; display: block",
                            ),
                            _style="width: 100%; text-align: center; margin-bottom: 25px;",
                        ),
                        P(B(current.T('THEN GO TO "For contributors —> Invitation(s) to review a preprint" IN THE TOP MENU'))),
                        P(B(current.T("OR")), _style="margin: 1em; text-align: center;"),
                        DIV(
                            A(
                                SPAN(
                                    current.T("DECLINE"),
                                    _style=button_style + "background: #c54b4b",
                                ),
                                _href=declineLinkTarget,
                                _style="text-decoration: none; display: block",
                            ),
                            _style="width: 100%; text-align: center; margin-bottom: 25px;",
                        ),
                    )
                    if hashtag_template == "#DefaultReviewInvitationNewUserStage2":
                        new_user_reminder_template = emailing_tools.getCorrectHashtag("#ReminderReviewerReviewInvitationNewUser", article)

                    create_reminder_for_reviewer_review_invitation_new_user(session, auth, db, review.id, replyto_addresses, reviewer_invitation_buttons=reviewer_invitation_buttons, hashtag_template=new_user_reminder_template, new_stage=new_stage)

                elif linkTarget:

                    if review.review_state is None or review.review_state == "Awaiting response" or review.review_state == "":

                        if declineLinkTarget:
                            reviewer_invitation_buttons = DIV(
                                P(B(current.T("TO ACCEPT OR DECLINE CLICK ON ONE OF THE FOLLOWING BUTTONS:"))),
                                DIV(
                                    A(
                                        SPAN(
                                            current.T("Yes, I would like to review this preprint"),
                                            _style=button_style + "background: #93c54b",
                                        ),
                                        _href=linkTarget,
                                        _style="text-decoration: none; display: block",
                                    ),
                                    B(current.T("OR")),
                                    A(
                                        SPAN(
                                            current.T("No thanks, I would rather not"),
                                            _style=button_style + "background: #f47c3c",
                                        ),
                                        _href=declineLinkTarget,
                                        _style="text-decoration: none; display: block",
                                    ),
                                    _style="width: 100%; text-align: center; margin-bottom: 25px;",
                                ),
                            )

                    elif review.review_state == "Awaiting review":
                        reviewer_invitation_buttons = DIV(P(B(current.T("TO WRITE, EDIT OR UPLOAD YOUR REVIEW CLICK ON THE FOLLOWING LINK:"))), A(linkTarget, _href=linkTarget))
                    
                    if hashtag_template == "#DefaultReviewInvitationRegisteredUserNewReviewerStage2":
                        reg_user_reminder_template = emailing_tools.getCorrectHashtag("#ReminderReviewInvitationRegisteredUserNewReviewer", article)
                    if hashtag_template == "#DefaultReviewInvitationRegisteredUserReturningReviewerStage2":
                        reg_user_reminder_template = emailing_tools.getCorrectHashtag("#ReminderReviewInvitationRegisteredUserReturningReviewer", article)

                    create_reminder_for_reviewer_review_invitation_registered_user(session, auth, db, review.id, replyto_addresses, reviewer_invitation_buttons=reviewer_invitation_buttons, new_round=new_round, hashtag_template=reg_user_reminder_template, new_stage=new_stage)

                subject_header = email_subject_header(recomm.article_id)
                subject_without_appname = subject.replace("%s: " % subject_header, "")
                applogo = URL("static", "images/small-background.png", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
                authors_reply = None
                if new_round:
                    prev_recomm = common_tools.get_prev_recomm(db, recomm)
                    authors_reply = emailing_parts.getAuthorsReplyHTML(auth, db, prev_recomm.id)

                message = render(
                    filename=MAIL_HTML_LAYOUT,
                    context=dict(
                        subject=subject_without_appname,
                        applogo=applogo,
                        appname=mail_vars["appName"],
                        content=XML(content),
                        footer=emailing_tools.mkFooter(db),
                        reviewer_invitation_buttons=reviewer_invitation_buttons,
                        authors_reply=authors_reply,
                    ),
                )

                mail_vars["ccAddresses"] = cc_addresses + emailing_vars.getCoRecommendersMails(db, recomm.id)
                mail_vars["replytoAddresses"] = replyto_addresses

                db.mail_queue.insert(
                    dest_mail_address=mail_vars["destAddress"],
                    cc_mail_addresses=mail_vars["ccAddresses"],
                    replyto_addresses=mail_vars["replytoAddresses"],
                    mail_subject=subject,
                    mail_content=message,
                    user_id=auth.user_id,
                    recommendation_id=recomm.id,
                    mail_template_hashtag=hashtag_template,
                    article_id=recomm.article_id,
                )

                if review.review_state is None:
                    review.review_state = "Awaiting response"
                    review.update_record()

                reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_to_recommender_reviewers_suggestions(session, auth, db, review, suggested_reviewers_text):
    mail_vars = emailing_tools.getMailCommonVars()
    reports = []

    recomm = db.t_recommendations[review.recommendation_id]
    if recomm:
        article = db.t_articles[recomm.article_id]
        if article:
            mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
            mail_vars["reviewerPerson"] = common_small_html.mkUserWithMail(auth, db, review.reviewer_id)
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["linkTarget"] = URL(
                c="recommender",
                f="my_recommendations",
                scheme=mail_vars["scheme"],
                host=mail_vars["host"],
                port=mail_vars["port"],
                vars=dict(pressReviews=article.already_published),
            )
    
            mail_vars["suggestedReviewersText"] = suggested_reviewers_text.strip().replace('\n','<br>')
    
            hashtag_template = emailing_tools.getCorrectHashtag("#RecommenderSuggestedReviewers", article)
            emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, recomm.article_id)
    
            reports = emailing_tools.createMailReport(True, mail_vars["destPerson"].flatten(), reports)
    
    emailing_tools.getFlashMessage(session, reports)

######################################################################################################################################################################
######################################################################################################################################################################
def send_change_mail(session, auth, db, userId, dest_mail, key):
    print("send_change_mail")
    mail = emailing_tools.getMailer(auth)
    mail_vars = emailing_tools.getMailCommonVars()

    mail_resu = False
    reports = []

    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, userId)
    mail_vars["destAddress"] = dest_mail
    mail_vars["verifyMailUrl"] = URL(c="default", f="user", args=["verify_email", key], scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

    hashtag_template = "#UserChangeMail"
    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars)

    reports = emailing_tools.createMailReport(True, mail_vars["destAddress"], reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_recover_mail(session, auth, db, userId, dest_mail, key):
    print("send_recover_mail")
    mail = emailing_tools.getMailer(auth)
    mail_vars = emailing_tools.getMailCommonVars()

    mail_resu = False
    reports = []

    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, userId)
    mail_vars["destAddress"] = dest_mail
    mail_vars["recoverMailUrl"] = URL(c="default", f="recover_mail", vars=dict(key=key), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

    hashtag_template = "#UserRecoverMail"
    emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars)

    reports = emailing_tools.createMailReport(True, mail_vars["destAddress"], reports)

    emailing_tools.getFlashMessage(session, reports)


######################################################################################################################################################################
def send_reviewer_generic_mail(session, auth, db, reviewer_email, recomm, form):


    cc_addresses = emailing_tools.list_addresses(form.cc)
    replyto_addresses = emailing_tools.list_addresses(form.replyto)
    form.subject
    form.message

    mail_content = mk_mail(form.subject, form.message)

    db.mail_queue.insert(
        user_id             = auth.user_id,
        dest_mail_address   = reviewer_email,
        replyto_addresses   = replyto_addresses,
        cc_mail_addresses   = cc_addresses,
        mail_subject        = form.subject,
        mail_content        = mail_content,

        article_id          = recomm.article_id,
        recommendation_id   = recomm.id,
        mail_template_hashtag = "#ReviewerGenericMail",
    )

    reports = emailing_tools.createMailReport(True, reviewer_email, reports=[])
    emailing_tools.getFlashMessage(session, reports)

######################################################################################################################################################################
def send_submitter_generic_mail(session, auth, db, author_email, articleId, form):


    cc_addresses = emailing_tools.list_addresses(form.cc)
    replyto_addresses = emailing_tools.list_addresses(form.replyto)
    form.subject
    form.message

    mail_content = mk_mail(form.subject, form.message)

    db.mail_queue.insert(
        user_id             = auth.user_id,
        dest_mail_address   = author_email,
        replyto_addresses   = replyto_addresses,
        cc_mail_addresses   = cc_addresses,
        mail_subject        = form.subject,
        mail_content        = mail_content,

        article_id          = articleId,
        mail_template_hashtag = "#SubmitterGenericMail",
    )

    reports = emailing_tools.createMailReport(True, author_email, reports=[])
    emailing_tools.getFlashMessage(session, reports)

def mk_mail(subject, message):
    mail_vars = emailing_tools.getMailCommonVars()
    applogo = URL("static", "images/small-background.png",
                    scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])
    subject_without_appname = subject.replace("%s: " % mail_vars["appName"], "")
    return render(
        filename=MAIL_HTML_LAYOUT,
        context=dict(
            applogo=applogo,
            appname=mail_vars["appName"],
            subject=subject_without_appname,
            content=XML(message),
        )
    )


######################################################################################################################################################################
## News letter
######################################################################################################################################################################
def send_newsletter_mail(session, auth, db, userId, newsletterType):
    mail_vars = emailing_tools.getMailCommonVars()

    user = db.auth_user[userId]

    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, userId)
    mail_vars["destAddress"] = user["email"]

    if newsletterType in ["Never", None]:
        hashtag_template = newsletter.template["Weekly"]
        newsletter_interval = 0
    else:
        hashtag_template = newsletter.template[newsletterType]
        newsletter_interval = newsletter.interval[newsletterType]

    newRecommendationsCount = 0
    newPreprintRequiringRecommenderCount = 0
    newPreprintSearchingForReviewersCount = 0
    if newsletter_interval is not None:
        # New recommended articles
        new_recommended_articles = db(
            (
                (db.t_articles.last_status_change >= (datetime.datetime.now() - datetime.timedelta(days=newsletter_interval)).date())
                & (db.t_recommendations.article_id == db.t_articles.id)
                & (db.t_recommendations.recommendation_state == "Recommended")
                & (db.t_articles.status == "Recommended")
            )
        ).select(db.t_articles.ALL, orderby=~db.t_articles.last_status_change)

        i = 0
        newRecommendations = DIV()
        newRecommendationsCount = len(new_recommended_articles)
        for article in new_recommended_articles:
            i += 1
            if i <= 5:
                newRecommendations.append(newsletter.makeArticleWithRecommRow(auth, db, article))

        # New preprint searching for reviewers
        new_searching_for_reviewers_preprint = db(
            (
                (db.t_articles.last_status_change >= (datetime.datetime.now() - datetime.timedelta(days=newsletter_interval)).date())
                & (db.t_articles.is_searching_reviewers == True)
                & (db.t_articles.status.belongs(("Under consideration", "Scheduled submission under consideration")))
            )
        ).select(db.t_articles.ALL, orderby=~db.t_articles.last_status_change)

        j = 0
        newPreprintSearchingForReviewers = DIV()
        newPreprintSearchingForReviewersCount = len(new_searching_for_reviewers_preprint)
        for article in new_searching_for_reviewers_preprint:
            j += 1
            if j <= 5:
                newPreprintSearchingForReviewers.append(newsletter.makeArticleRow(article, "review"))

        # New preprint requiring recommender
        group = db((db.auth_user.id == userId) & (db.auth_membership.user_id == db.auth_user.id) & (db.auth_membership.group_id == 2)).count()

        newPreprintRequiringRecommender = None
        if group > 0:
            new_searching_for_recommender_preprint = db(
                (
                    (db.t_articles.last_status_change >= (datetime.datetime.now() - datetime.timedelta(days=newsletter_interval)).date())
                    & (db.t_articles.status == "Awaiting consideration")
                )
            ).select(db.t_articles.ALL, orderby=~db.t_articles.last_status_change)

            k = 0
            newPreprintRequiringRecommender = DIV()
            newPreprintRequiringRecommenderCount = len(new_searching_for_recommender_preprint)
            for article in new_searching_for_recommender_preprint:
                k += 1
                if k <= 5:
                    newPreprintRequiringRecommender.append(newsletter.makeArticleRow(article, "recommendation"))

    if (newRecommendationsCount > 0) or (newPreprintSearchingForReviewersCount > 0) or (newPreprintRequiringRecommenderCount > 0):
        emailing_tools.insertNewsLetterMailInQueue(
            auth,
            db,
            mail_vars,
            hashtag_template,
            newRecommendations=newRecommendations,
            newRecommendationsCount=newRecommendationsCount,
            newPreprintSearchingForReviewers=newPreprintSearchingForReviewers,
            newPreprintSearchingForReviewersCount=newPreprintSearchingForReviewersCount,
            newPreprintRequiringRecommender=newPreprintRequiringRecommender,
            newPreprintRequiringRecommenderCount=newPreprintRequiringRecommenderCount,
        )


######################################################################################################################################################################
def delete_newsletter_mail(session, auth, db, userId):
    user = db.auth_user[userId]

    if user is not None:
        db(
            (
                (db.mail_queue.dest_mail_address == user.email)
                & (
                    (db.mail_queue.mail_template_hashtag == "#NewsLetterWeekly")
                    | (db.mail_queue.mail_template_hashtag == "#NewsLetterEveryTwoWeeks")
                    | (db.mail_queue.mail_template_hashtag == "#NewsLetterMonthly")
                )
            )
        ).delete()


######################################################################################################################################################################
## Reminders
######################################################################################################################################################################
def create_reminder_for_submitter_suggested_recommender_needed(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    sugg_recommenders = db(db.t_suggested_recommenders.article_id == articleId).select()

    if article and article.user_id is not None and len(sugg_recommenders) == 0:

        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]
        mail_vars["ethicsLink"] = mk_ethicsLink()

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderSubmitterSuggestedRecommenderNeeded", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, None, None, articleId)


def mk_ethicsLink():
    mail_vars = emailing_tools.getMailCommonVars()
    return URL("about", "ethics", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])


######################################################################################################################################################################
def create_reminder_for_submitter_new_suggested_recommender_needed(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    if article and article.user_id is not None:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderSubmitterNewSuggestedRecommenderNeeded", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, None, None, articleId)


######################################################################################################################################################################
def create_reminder_for_submitter_cancel_submission(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    if article and article.user_id is not None:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderSubmitterCancelSubmission", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, None, None, articleId)


######################################################################################################################################################################
def create_reminder_for_submitter_revised_version_warning(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()

    if article and recomm:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderSubmitterRevisedVersionWarning", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, articleId)


######################################################################################################################################################################
def create_reminder_for_submitter_revised_version_needed(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()

    if article and recomm:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderSubmitterRevisedVersionNeeded", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, articleId)


######################################################################################################################################################################
def create_reminder_for_submitter_scheduled_submission_soon_due(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()
    mail_vars["linkTarget"] = mk_submitter_my_articles_url(mail_vars)

    article = db.t_articles[articleId]

    recommId = None
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()
    if recomm:
        recommId = recomm.id
        mail_vars["recommenderPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

    if article:
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        # do not user getCorrectHashtag here to avoid fake name
        hashtag_template = "#ReminderSubmitterScheduledSubmissionSoonDue"
        scheduled_submission_date = getScheduledSubmissionDate(article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recommId, None, articleId, sending_date_forced=(scheduled_submission_date - datetime.timedelta(days=14)))

######################################################################################################################################################################
def create_reminder_for_submitter_scheduled_submission_due(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()
    mail_vars["linkTarget"] = mk_submitter_my_articles_url(mail_vars)

    article = db.t_articles[articleId]

    recommId = None
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()
    if recomm:
        recommId = recomm.id
        mail_vars["recommenderPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

    if article:
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        # do not user getCorrectHashtag here to avoid fake name
        hashtag_template = "#ReminderSubmitterScheduledSubmissionDue"
        scheduled_submission_date = getScheduledSubmissionDate(article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recommId, None, articleId, sending_date_forced=scheduled_submission_date)

######################################################################################################################################################################
def create_reminder_for_submitter_scheduled_submission_over_due(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()
    mail_vars["linkTarget"] = mk_submitter_my_articles_url(mail_vars)

    article = db.t_articles[articleId]

    recommId = None
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()
    if recomm:
        recommId = recomm.id
        mail_vars["recommenderPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

    if article:
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, article.user_id)
        mail_vars["destAddress"] = db.auth_user[article.user_id]["email"]

        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        # do not user getCorrectHashtag here to avoid fake name
        hashtag_template = "#ReminderSubmitterScheduledSubmissionOverDue"
        scheduled_submission_date = getScheduledSubmissionDate(article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recommId, None, articleId, sending_date_forced=(scheduled_submission_date + datetime.timedelta(days=1)))


def mk_submitter_my_articles_url(mail_vars):
    return URL(c="user", f="my_articles",
            scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])


######################################################################################################################################################################
def delete_reminder_for_submitter(db, hashtag_template, articleId):
    article = db.t_articles[articleId]
    if article and article.user_id is not None:
        submitter_mail = db.auth_user[article.user_id]["email"]

        db((db.mail_queue.dest_mail_address == submitter_mail) & (db.mail_queue.mail_template_hashtag == hashtag_template) & (db.mail_queue.article_id == articleId)).delete()
        if pciRRactivated:
            hashtag_template_rr = hashtag_template + "Stage"
            db(
                (db.mail_queue.dest_mail_address == submitter_mail)
                & (db.mail_queue.mail_template_hashtag.startswith(hashtag_template_rr))
                & (db.mail_queue.article_id == articleId)
            ).delete()


######################################################################################################################################################################
def create_reminder_for_suggested_recommenders_invitation(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    if article:
        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        suggested_recommenders = db(
            (db.t_suggested_recommenders.article_id == articleId)
            & (db.t_suggested_recommenders.declined == False)
            & (db.t_suggested_recommenders.suggested_recommender_id == db.auth_user.id)
        ).select(db.t_suggested_recommenders.ALL, db.auth_user.ALL)

        for sugg_recommender in suggested_recommenders:
            hashtag_template = emailing_tools.getCorrectHashtag("#ReminderSuggestedRecommenderInvitation", article)

            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, sugg_recommender["auth_user.id"])
            mail_vars["destAddress"] = db.auth_user[sugg_recommender["auth_user.id"]]["auth_user.email"]

            mail_vars["articleDoi"] = article.doi
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleAuthors"] = mkAuthors(article)
            mail_vars["linkTarget"] = URL(
                c="recommender", f="article_details", vars=dict(articleId=article.id), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"]
            )
            mail_vars["helpUrl"] = URL(c="help", f="help_generic", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

            emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, None, None, articleId)


######################################################################################################################################################################
def create_reminder_for_suggested_recommender_invitation(session, auth, db, articleId, suggRecommId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    if article:
        if pciRRactivated:
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderSuggestedRecommenderInvitation", article)

        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, suggRecommId)
        mail_vars["destAddress"] = db.auth_user[suggRecommId]["email"]

        mail_vars["articleDoi"] = article.doi
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = mkAuthors(article)

        mail_vars["linkTarget"] = URL(
            c="recommender", f="article_details", vars=dict(articleId=article.id), scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"]
        )
        mail_vars["helpUrl"] = URL(c="help", f="help_generic", scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, None, None, articleId)


######################################################################################################################################################################
def delete_reminder_for_suggested_recommenders(db, hashtag_template, articleId):
    article = db.t_articles[articleId]
    if article:
        suggested_recommenders = db(
            (db.t_suggested_recommenders.article_id == articleId)
            & (db.t_suggested_recommenders.declined == False)
            & (db.t_suggested_recommenders.suggested_recommender_id == db.auth_user.id)
        ).select(db.t_suggested_recommenders.ALL, db.auth_user.ALL)

        for sugg_recommender in suggested_recommenders:
            db(
                (db.mail_queue.dest_mail_address == sugg_recommender["auth_user.email"])
                & (db.mail_queue.mail_template_hashtag == hashtag_template)
                & (db.mail_queue.article_id == articleId)
            ).delete()

            if pciRRactivated:
                hashtag_template_rr = hashtag_template + "Stage"
                db(
                    (db.mail_queue.dest_mail_address == sugg_recommender["auth_user.email"])
                    & (db.mail_queue.mail_template_hashtag.startswith(hashtag_template_rr))
                    & (db.mail_queue.article_id == articleId)
                ).delete()


######################################################################################################################################################################
def delete_reminder_for_one_suggested_recommender(db, hashtag_template, articleId, suggRecommId):
    article = db.t_articles[articleId]
    if article:
        db(
            (db.mail_queue.dest_mail_address == db.auth_user[suggRecommId]["email"])
            & (db.mail_queue.mail_template_hashtag == hashtag_template)
            & (db.mail_queue.article_id == articleId)
        ).delete()

        if pciRRactivated:
            hashtag_template_rr = hashtag_template + "Stage"
            db(
                (db.mail_queue.dest_mail_address == db.auth_user[suggRecommId]["email"])
                & (db.mail_queue.mail_template_hashtag.startswith(hashtag_template_rr))
                & (db.mail_queue.article_id == articleId)
            ).delete()


###############################################################################
def reviewLink(**kwargs):
    mail_vars = emailing_tools.getMailCommonVars()
    return URL(c="user", f="my_reviews", vars=kwargs, scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"])


######################################################################################################################################################################
def create_reminder_for_reviewer_review_invitation_new_user(session, auth, db, reviewId, replyto_addresses, reviewer_invitation_buttons=None, hashtag_template=None, new_stage=False):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db.t_articles[recomm.article_id]

    if review and recomm and article:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, review.reviewer_id)
        mail_vars["destAddress"] = db.auth_user[review.reviewer_id]["email"]
        mail_vars["description"] = myconf.take("app.description")
        mail_vars["sender"] = mkSender(auth, db, recomm)

        mail_vars["art_doi"] = article.doi
        mail_vars["art_title"] = md_to_html(article.title)
        
        mail_vars["articleDoi"] = article.doi
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = mkAuthors(article)
        mail_vars["myReviewsLink"] = reviewLink(pendingOnly=True)
        mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        
        mail_vars["reviewDuration"] = (review.review_duration).lower()

        if article.art_stage_1_id is not None:
            stage1_art = db.t_articles[article.art_stage_1_id]
            report_survey = article.t_report_survey.select().last()
            mail_vars["Stage2_Stage1recommendationtext"] = emailing_vars.getPCiRRrecommendationText(db, stage1_art)
            mail_vars["Stage1_registeredURL"] = report_survey.q30
            mail_vars["Stage2vsStage1_trackedchangesURL"] = report_survey.tracked_changes_url

        if pciRRactivated:
            mail_vars.update(getPCiRRinvitationTexts(stage1_art if new_stage else article, new_stage))
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        mail_vars["parallelText"] = ""
        if parallelSubmissionAllowed:
            mail_vars[
                "parallelText"
            ] += """Note that if the authors abandon the process at %(appLongName)s after reviewers have written their reports, we will post the reviewers' reports on the %(appLongName)s website as recognition of their work and in order to enable critical discussion.""" % mail_vars
            if article.parallel_submission:
                mail_vars[
                    "parallelText"
                ] += """Note: The authors have chosen to submit their manuscript elsewhere in parallel. We still believe it is useful to review their work at %(appLongName)s, and hope you will agree to review this preprint.""" % mail_vars

        mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)
        mail_vars["replytoAddresses"] = replyto_addresses
       
        if hashtag_template is None:
            hashtag_template = emailing_tools.getCorrectHashtag("#ReminderReviewerReviewInvitationNewUser", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id, reviewer_invitation_buttons=reviewer_invitation_buttons)


######################################################################################################################################################################
def create_reminder_for_reviewer_review_invitation_registered_user(session, auth, db, reviewId, replyto_addresses, reviewer_invitation_buttons=None, new_round=False, hashtag_template=None, new_stage=False):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db.t_articles[recomm.article_id]

    if review and recomm and article:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, review.reviewer_id)
        mail_vars["destAddress"] = db.auth_user[review.reviewer_id]["email"]
        mail_vars["sender"] = mkSender(auth, db, recomm)
        
        mail_vars["art_doi"] = article.doi
        mail_vars["art_title"] = md_to_html(article.title)
        mail_vars["description"] = myconf.take("app.description")

        mail_vars["articleDoi"] = article.doi
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = mkAuthors(article)
        mail_vars["myReviewsLink"] = reviewLink(pendingOnly=True)
        mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["reviewDuration"] = (review.review_duration).lower()
        mail_vars["replytoAddresses"] = replyto_addresses

        _recomm = common_tools.get_prev_recomm(db, recomm) if new_round else recomm
        r2r_url, trackchanges_url = emailing_parts.getAuthorsReplyLinks(auth, db, _recomm.id)

        r2r_url = str(r2r_url) if r2r_url else "(no author's reply)"
        trackchanges_url = str(trackchanges_url) if trackchanges_url else "(no tracking)"

        mail_vars["r2r_url"] = r2r_url
        mail_vars["trackchanges_url"] = trackchanges_url

        if article.art_stage_1_id is not None:
            stage1_art = db.t_articles[article.art_stage_1_id]
            report_survey = article.t_report_survey.select().last()
            mail_vars["Stage2_Stage1recommendationtext"] = emailing_vars.getPCiRRrecommendationText(db, stage1_art)
            mail_vars["Stage1_registeredURL"] = report_survey.q30
            mail_vars["Stage2vsStage1_trackedchangesURL"] = report_survey.tracked_changes_url

        if pciRRactivated:
            mail_vars.update(getPCiRRinvitationTexts(stage1_art if new_stage else article, new_stage))
            mail_vars.update(getPCiRRScheduledSubmissionsVars(article))

        mail_vars["parallelText"] = ""
        if parallelSubmissionAllowed:
            mail_vars[
                "parallelText"
            ] += """Note that if the authors abandon the process at %(appLongName)s after reviewers have written their reports, we will post the reviewers' reports on the %(appLongName)s website as recognition of their work and in order to enable critical discussion.""" % mail_vars
            if article.parallel_submission:
                mail_vars[
                    "parallelText"
                ] += """Note: The authors have chosen to submit their manuscript elsewhere in parallel. We still believe it is useful to review their work at %(appLongName)s, and hope you will agree to review this preprint.""" % mail_vars

        mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

        if hashtag_template is  None:
            hashtag_template = emailing_tools.getCorrectHashtag("#ReminderReviewerReviewInvitationRegisteredUser", article)
        authors_reply = None
        if new_round:
            hashtag_template = emailing_tools.getCorrectHashtag("#ReminderReviewerInvitationNewRoundRegisteredUser", article)
            prev_recomm = common_tools.get_prev_recomm(db, recomm)
            authors_reply = emailing_parts.getAuthorsReplyHTML(auth, db, prev_recomm.id)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id, reviewer_invitation_buttons=reviewer_invitation_buttons, authors_reply=authors_reply)


######################################################################################################################################################################
def create_reminder_for_reviewer_review_soon_due(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db.t_articles[recomm.article_id]

    if review and recomm and article:
        if scheduledSubmissionActivated and ((article.scheduled_submission_date is not None) or (article.status.startswith("Scheduled submission"))):
            print("Nope")
        else:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, review.reviewer_id)
            mail_vars["destAddress"] = db.auth_user[review.reviewer_id]["email"]

            mail_vars["articleDoi"] = article.doi
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleAuthors"] = mkAuthors(article)
            mail_vars["myReviewsLink"] = reviewLink()
            mail_vars["reviewDueDate"] = str((datetime.datetime.now() + datetime.timedelta(days=get_review_days(review.review_duration))).strftime(DEFAULT_DATE_FORMAT))
            mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

            mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

            if isScheduledTrack(article):
                mail_vars["reviewDueDate"] = due_date = getScheduledReviewDueDate(article)
                base_sending_date = datetime.datetime.strptime(due_date, DEFAULT_DATE_FORMAT)
            else:
                base_sending_date = None

            hashtag_template = emailing_tools.getCorrectHashtag("#ReminderReviewerReviewSoonDue", article)

            emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id, reviewId, base_sending_date=base_sending_date)


def isScheduledTrack(art):
    report_survey = art.t_report_survey.select().last()
    return report_survey and report_survey.q10


def getScheduledSubmissionDate(article):
    return article.t_report_survey.select().last().q10


def getScheduledReviewDueDate(article):
    _ = getPCiRRScheduledSubmissionsVars(article)
    return _["scheduledReviewDueDate"]


######################################################################################################################################################################
def create_reminder_for_reviewer_review_due(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db.t_articles[recomm.article_id]

    if review and recomm and article:
        if scheduledSubmissionActivated and ((article.scheduled_submission_date is not None) or (article.status.startswith("Scheduled submission"))):
            print("Nope")
        else:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, review.reviewer_id)
            mail_vars["destAddress"] = db.auth_user[review.reviewer_id]["email"]
            
            mail_vars["myReviewsLink"] = reviewLink()
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleAuthors"] = mkAuthors(article)
            mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

            mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

            if isScheduledTrack(article):
                mail_vars["reviewDueDate"] = due_date = getScheduledReviewDueDate(article)
                base_sending_date = datetime.datetime.strptime(due_date, DEFAULT_DATE_FORMAT)
            else:
                base_sending_date = None

            hashtag_template = emailing_tools.getCorrectHashtag("#ReminderReviewerReviewDue", article)

            emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id, reviewId, base_sending_date=base_sending_date)


######################################################################################################################################################################
def create_reminder_for_reviewer_review_over_due(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db.t_articles[recomm.article_id]

    if review and recomm and article:
        if scheduledSubmissionActivated and ((article.scheduled_submission_date is not None) or (article.status.startswith("Scheduled submission"))):
            print("Nope")
        else:
            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, review.reviewer_id)
            mail_vars["destAddress"] = db.auth_user[review.reviewer_id]["email"]

            mail_vars["myReviewsLink"] = reviewLink()
            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleAuthors"] = mkAuthors(article)
            mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

            mail_vars["ccAddresses"] = [db.auth_user[recomm.recommender_id]["email"]] + emailing_vars.getCoRecommendersMails(db, recomm.id)

            if isScheduledTrack(article):
                mail_vars["reviewDueDate"] = due_date = getScheduledReviewDueDate(article)
                base_sending_date = datetime.datetime.strptime(due_date, DEFAULT_DATE_FORMAT)
            else:
                base_sending_date = None

            hashtag_template = emailing_tools.getCorrectHashtag("#ReminderReviewerReviewOverDue", article)

            emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id, reviewId, base_sending_date=base_sending_date)


######################################################################################################################################################################
def create_reminder_for_reviewer_scheduled_review_coming_soon(session, auth, db, review):
    recomm = db.t_recommendations[review.recommendation_id]
    article = db.t_articles[recomm.article_id]
    reviewer = db.auth_user[review.reviewer_id]

    if not reviewer: return
    if not review.review_state == "Awaiting review": return

    mail_vars = emailing_tools.getMailCommonVars()
    mail_vars.update(getPCiRRScheduledSubmissionsVars(article))
    mail_vars.update({
        "destPerson": common_small_html.mkUser(auth, db, reviewer.id),
        "destAddress": reviewer.email,
        "articleTitle": md_to_html(article.title),
        "articleAuthors": mkAuthors(article),
        "recommenderPerson": mk_recommender(auth, db, article),
        "reviewDueDate": mail_vars["scheduledReviewDueDate"],
        "myReviewsLink": reviewLink(),
    })

    sending_date = getScheduledSubmissionDate(article) # = LatestReviewStartDate minus 1 week
    hashtag_template = "#ReminderScheduledReviewComingSoon"

    emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id, review.id, sending_date_forced=sending_date)


######################################################################################################################################################################
def delete_reminder_for_reviewer(db, hashtag_template, reviewId):
    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    reviewer = db.auth_user[review.reviewer_id]

    for hashtag in hashtag_template:
        if reviewer and recomm:
            db((db.mail_queue.dest_mail_address == reviewer.email) & (db.mail_queue.mail_template_hashtag == hashtag) & (db.mail_queue.recommendation_id == recomm.id)).delete()

            if pciRRactivated:
                hashtag_template_rr = hashtag + "Stage"
                db(
                    (db.mail_queue.dest_mail_address == reviewer.email)
                    & (db.mail_queue.mail_template_hashtag.startswith(hashtag_template_rr))
                    & (db.mail_queue.recommendation_id == recomm.id)
                ).delete()


######################################################################################################################################################################
def create_reminder_for_recommender_reviewers_needed(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()
    recommCount = db((db.t_recommendations.article_id == article.id)).count()

    if recomm and article and recommCount == 1:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

        mail_vars["articleAuthors"] = article.authors
        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

        mail_vars["reviewDuration"] = default_review_duration.lower()

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderRecommenderReviewersNeeded", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)


######################################################################################################################################################################
def create_reminder_for_recommender_new_reviewers_needed(session, auth, db, recommId):
    mail_vars = emailing_tools.getMailCommonVars()

    recomm = db.t_recommendations[recommId]
    article = db((db.t_articles.id == recomm.article_id)).select().last()
    recommCount = db((db.t_recommendations.article_id == article.id)).count()

    if recomm and article and recommCount == 1:
        count_reviews_under_consideration = db(
            (db.t_reviews.recommendation_id == recommId) & ((db.t_reviews.review_state == "Awaiting review") | (db.t_reviews.review_state == "Review completed"))
        ).count()
        if count_reviews_under_consideration < 2:

            mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
            mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

            mail_vars["articleTitle"] = md_to_html(article.title)
            mail_vars["articleAuthors"] = article.authors
            mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

            hashtag_template = emailing_tools.getCorrectHashtag("#ReminderRecommenderNewReviewersNeeded", article)

            emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)


######################################################################################################################################################################
def create_reminder_for_recommender_decision_soon_due(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db((db.t_articles.id == recomm.article_id)).select().last()

    count_reviews_completed = 0
    count_reviews_under_consideration = 0
    if recomm:
        count_reviews_completed = db((db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Review completed")).count()
        count_reviews_under_consideration = db((db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Awaiting review")).count()

    if recomm and count_reviews_completed >= 1 and count_reviews_under_consideration == 1 and article:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderRecommenderDecisionSoonDue", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, recomm.article_id)


######################################################################################################################################################################
def create_reminder_for_recommender_decision_due(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db((db.t_articles.id == recomm.article_id)).select().last()

    count_reviews_completed = 0
    count_reviews_under_consideration = 0
    if recomm:
        count_reviews_completed = db((db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Review completed")).count()
        count_reviews_under_consideration = db((db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Awaiting review")).count()

    if recomm and count_reviews_completed >= 1 and count_reviews_under_consideration == 1 and article:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderRecommenderDecisionDue", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, recomm.article_id)


######################################################################################################################################################################
def create_reminder_for_recommender_decision_over_due(session, auth, db, reviewId):
    mail_vars = emailing_tools.getMailCommonVars()

    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    article = db((db.t_articles.id == recomm.article_id)).select().last()

    count_reviews_completed = 0
    count_reviews_under_consideration = 0
    if recomm:
        count_reviews_completed = db((db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Review completed")).count()
        count_reviews_under_consideration = db((db.t_reviews.recommendation_id == recomm.id) & (db.t_reviews.review_state == "Awaiting review")).count()

    if recomm and count_reviews_completed >= 1 and count_reviews_under_consideration == 1 and article:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderRecommenderDecisionOverDue", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, recomm.article_id)


######################################################################################################################################################################
def create_reminder_for_recommender_revised_decision_soon_due(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()

    if recomm and article:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = article.authors
        mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

        mail_vars["ccAddresses"] = emailing_vars.getCoRecommendersMails(db, recomm.id)

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderRecommenderRevisedDecisionSoonDue", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)


######################################################################################################################################################################
def create_reminder_for_recommender_revised_decision_due(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()

    if recomm and article:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = article.authors
        mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

        mail_vars["ccAddresses"] = emailing_vars.getCoRecommendersMails(db, recomm.id)

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderRecommenderRevisedDecisionDue", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)


######################################################################################################################################################################
def create_reminder_for_recommender_revised_decision_over_due(session, auth, db, articleId):
    mail_vars = emailing_tools.getMailCommonVars()

    article = db.t_articles[articleId]
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()

    if recomm and article:
        mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
        mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

        mail_vars["articleTitle"] = md_to_html(article.title)
        mail_vars["articleAuthors"] = article.authors
        mail_vars["recommenderName"] = common_small_html.mkUser(auth, db, recomm.recommender_id)

        mail_vars["ccAddresses"] = emailing_vars.getCoRecommendersMails(db, recomm.id)

        hashtag_template = emailing_tools.getCorrectHashtag("#ReminderRecommenderRevisedDecisionOverDue", article)

        emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)


######################################################################################################################################################################
def delete_reminder_for_recommender(db, hashtag_template, recommendationId, force_delete=False):
    recomm = db.t_recommendations[recommendationId]

    if recomm:
        recomm_mail = db.auth_user[recomm.recommender_id]["email"]

        if (
            hashtag_template in (
                "#ReminderRecommenderNewReviewersNeeded",
                "#ReminderRecommenderNewReviewersNeededStage1",
                "#ReminderRecommenderNewReviewersNeededStage2",
                "#ReminderRecommender2ReviewsReceivedCouldMakeDecision",
            )
            and not force_delete
        ):
            count_reviews_under_consideration = db(
                (db.t_reviews.recommendation_id == recommendationId) & ((db.t_reviews.review_state == "Awaiting review") | (db.t_reviews.review_state == "Review completed"))
            ).count()
            if count_reviews_under_consideration >= 1:
                db(
                    (db.mail_queue.dest_mail_address == recomm_mail) & (db.mail_queue.mail_template_hashtag == hashtag_template) & (db.mail_queue.recommendation_id == recomm.id)
                ).delete()

                if pciRRactivated:
                    hashtag_template_rr = hashtag_template + "Stage"
                    db(
                        (db.mail_queue.dest_mail_address == recomm_mail)
                        & (db.mail_queue.mail_template_hashtag.startswith(hashtag_template_rr))
                        & (db.mail_queue.recommendation_id == recomm.id)
                    ).delete()

        elif hashtag_template in (
            "#ReminderRecommenderRevisedDecisionSoonDue",
            "#ReminderRecommenderRevisedDecisionDue",
            "#ReminderRecommenderRevisedDecisionOverDue",
            "#ReminderRecommenderRevisedDecisionSoonDueStage1",
            "#ReminderRecommenderRevisedDecisionDueStage1",
            "#ReminderRecommenderRevisedDecisionOverDueStage1",
            "#ReminderRecommenderRevisedDecisionSoonDueStage2",
            "#ReminderRecommenderRevisedDecisionDueStage2",
            "#ReminderRecommenderRevisedDecisionOverDueStage2",
        ):
            article = db.t_articles[recomm.article_id]
            db(
                (db.mail_queue.dest_mail_address == recomm_mail) & (db.mail_queue.mail_template_hashtag == hashtag_template) & (db.mail_queue.article_id == recomm.article_id)
            ).delete()

            if pciRRactivated:
                hashtag_template_rr = hashtag_template + "Stage"
                db(
                    (db.mail_queue.dest_mail_address == recomm_mail)
                    & (db.mail_queue.mail_template_hashtag.startswith(hashtag_template_rr))
                    & (db.mail_queue.article_id == recomm.article_id)
                ).delete()

        else:
            db(
                (db.mail_queue.dest_mail_address == recomm_mail) & (db.mail_queue.mail_template_hashtag == hashtag_template) & (db.mail_queue.recommendation_id == recomm.id)
            ).delete()

            if pciRRactivated:
                hashtag_template_rr = hashtag_template + "Stage"
                db(
                    (db.mail_queue.dest_mail_address == recomm_mail)
                    & (db.mail_queue.mail_template_hashtag.startswith(hashtag_template_rr))
                    & (db.mail_queue.recommendation_id == recomm.id)
                ).delete()


######################################################################################################################################################################
def delete_reminder_for_recommender_from_article_id(db, hashtag_template, articleId):
    article = db.t_articles[articleId]
    recomm = db((db.t_recommendations.article_id == article.id)).select().last()

    if recomm:
        recomm_mail = db.auth_user[recomm.recommender_id]["email"]
        db((db.mail_queue.dest_mail_address == recomm_mail) & (db.mail_queue.mail_template_hashtag == hashtag_template) & (db.mail_queue.article_id == articleId)).delete()

        if pciRRactivated:
            hashtag_template_rr = hashtag_template + "Stage"
            db(
                (db.mail_queue.dest_mail_address == recomm_mail) & (db.mail_queue.mail_template_hashtag.startswith(hashtag_template_rr)) & (db.mail_queue.article_id == articleId)
            ).delete()


######################################################################################################################################################################
def delete_all_reminders_from_article_id(db, articleId):
    article = db.t_articles[articleId]
    if article:
        db((db.mail_queue.article_id == articleId) & (db.mail_queue.mail_template_hashtag.startswith("#Reminder"))).delete()


#####################################################################################################################################################################
def delete_all_reminders_from_recommendation_id(db, recommendationId):
    recomm = db.t_recommendations[recommendationId]
    if recomm:
        db((db.mail_queue.recommendation_id == recommendationId) & (db.mail_queue.mail_template_hashtag.startswith("#Reminder"))).delete()


######################################################################################################################################################################
# RESET PASSWORD EMAIL
def send_to_reset_password(session, auth, db, userId):
    print("send_reset_password")
    mail = emailing_tools.getMailer(auth)
    mail_vars = emailing_tools.getMailCommonVars()

    mail_resu = False
    reports = []

    fkey = db.auth_user[userId]["reset_password_key"]
    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, userId)
    mail_vars["destAddress"] = db.auth_user[userId]["email"]
    mail_vars["siteName"] = mail_vars["appName"]
    mail_vars["linkTarget"] = URL(
        c="default", f="user", args=["reset_password"], scheme=mail_vars["scheme"], host=mail_vars["host"], port=mail_vars["port"], vars=dict(key=fkey)
    )  # default/user/reset_password?key=1561727068-2946ea7b-54fe-4caa-87af-9c5e459b3487.
    mail_vars["linkTargetA"] = A(mail_vars["linkTarget"], _href=mail_vars["linkTarget"])

    mail = emailing_tools.buildMail(db, "#UserResetPassword", mail_vars)

    try:
        mail_resu = mail.send(to=[mail_vars["destAddress"]], subject=mail["subject"], message=mail["content"])
    except:
        pass

    reports = emailing_tools.createMailReport(mail_resu, mail_vars["destPerson"].flatten(), reports)
    time.sleep(MAIL_DELAY)

    emailing_tools.getFlashMessage(session, reports)

######################################################################################################################################################################
def check_mail_queue(db, hashtag, reviewer_mail, recomm_id):
    hashtag = hashtag + "%"
    return db(
            db.mail_queue.mail_template_hashtag.like(hashtag)
         & (db.mail_queue.dest_mail_address==reviewer_mail)
         & (db.mail_queue.recommendation_id==recomm_id)
    ).count() > 0

######################################################################################################################################################################
def create_cancellation_for_reviewer(session, auth, db, reviewId):

    mail_vars = emailing_tools.getMailCommonVars()
    reports = []
    review = db.t_reviews[reviewId]
    recomm = db.t_recommendations[review.recommendation_id]
    art = db.t_articles[recomm.article_id]
    reviewer = db.auth_user[review.reviewer_id]
    sender = None

    if not reviewer: # dest reviewer might have been deleted
        return

    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, reviewer.id).flatten()
    mail_vars["replytoAddresses"] = mail_vars["appContactMail"]
    mail_vars["ccAddresses"] = mail_vars["appContactMail"]
    mail_vars["destAddress"] = reviewer.email
    mail_vars["sender"] = mkSender(auth, db, recomm)
    mail_vars["art_doi"] = common_small_html.mkLinkDOI(recomm.doi or art.doi)
    mail_vars["art_title"] = md_to_html(art.title)
    mail_vars["art_authors"] = mkAuthors(art)

    mail_vars.update({
        "articleTitle": mail_vars["art_title"],
        "articleDoi": mail_vars["art_doi"],
        "articleAuthors": mail_vars["art_authors"],
    })

    if pciRRactivated:
        mail_vars.update(getPCiRRScheduledSubmissionsVars(art))

    hashtag_template = emailing_tools.getCorrectHashtag("#DefaultReviewCancellation", art)
    if check_mail_queue(db, hashtag_template, reviewer.email, review.recommendation_id) is False:
        emailing_tools.insertMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, recomm.article_id)
        reports = emailing_tools.createMailReport(True, mail_vars["destPerson"], reports)
        emailing_tools.getFlashMessage(session, reports)

######################################################################################################################################################################
def create_reminder_recommender_could_make_decision(session, auth, db, recommId):
    mail_vars = emailing_tools.getMailCommonVars()

    recomm = db.t_recommendations[recommId]
    article = db.t_articles[recomm.article_id]

    mail_vars["destPerson"] = common_small_html.mkUser(auth, db, recomm.recommender_id)
    mail_vars["destAddress"] = db.auth_user[recomm.recommender_id]["email"]

    mail_vars["articleTitle"] = md_to_html(article.title)
    mail_vars["articleAuthors"] = mkAuthors(article)

    mail_vars["ccAddresses"] = emailing_vars.getManagersMails(db)

    hashtag_template = "#ReminderRecommender2ReviewsReceivedCouldMakeDecision"

    emailing_tools.insertReminderMailInQueue(auth, db, hashtag_template, mail_vars, recomm.id, None, article.id)
