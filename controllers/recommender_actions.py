# -*- coding: utf-8 -*-

from app_modules.helper import *
from app_modules import emailing



######################################################################################################################################################################
## Actions

######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender"))
def do_cancel_press_review():
    recommId = request.vars["recommId"]
    if recommId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    recomm = db.t_recommendations[recommId]
    if recomm is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    art = db.t_articles[recomm.article_id]
    if art is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    # NOTE: security hole possible by changing manually articleId value: Enforced checkings below.
    if recomm.recommender_id != auth.user_id:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    else:
        art.status = "Cancelled"
        art.update_record()
        redirect(URL(c="recommender", f="my_recommendations", vars=dict(pressReviews=True)))


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def del_contributor():
    pressId = request.vars["pressId"]
    if pressId:
        if auth.has_membership(role="recommender"):
            if (
                db(
                    (db.t_press_reviews.id == pressId) & (db.t_recommendations.id == db.t_press_reviews.recommendation_id) & (db.t_recommendations.recommender_id == auth.user_id)
                ).count()
                > 0
            ):
                db((db.t_press_reviews.id == pressId)).delete()
        if auth.has_membership(role="manager"):
            db((db.t_press_reviews.id == pressId)).delete()

    redirect(request.env.http_referer)


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender"))
def do_accept_new_article_to_recommend():
    theUser = db.auth_user[auth.user_id]
    if "ethics_approved" in request.vars:
        theUser.ethical_code_approved = True
        theUser.update_record()
    if not (theUser.ethical_code_approved):
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    if "no_conflict_of_interest" not in request.vars:
        raise HTTP(403, "403: " + T("Forbidden"))
    noConflict = request.vars["no_conflict_of_interest"]
    if noConflict != "yes":
        raise HTTP(403, "403: " + T("Forbidden"))

    articleId = request.vars["articleId"]
    article = db.t_articles[articleId]

    if article.status == "Awaiting consideration":
        recommId = db.t_recommendations.insert(article_id=articleId, recommender_id=auth.user_id, doi=article.doi, recommendation_state="Ongoing", no_conflict_of_interest=True, ms_version=article.ms_version)
        db.commit()
        article = db.t_articles[articleId]  # reload due to trigger!
        article.status = "Under consideration"
        article.update_record()
        redirect(URL(c="recommender", f="reviewers", vars=dict(recommId=recommId)))
    else:
        if article.status == "Under consideration":
            lastRecomm = db((db.t_recommendations.article_id == articleId) & (db.t_recommendations.is_closed == False)).select(db.t_recommendations.ALL)
            if lastRecomm is not None and lastRecomm.id is not None:
                recommId = lastRecomm.id
                reviewersListSel = db((db.t_reviews.recommendation_id == recommId) & (db.t_reviews.reviewer_id == db.auth_user.id)).select(
                    db.t_reviews.id, db.t_reviews.review_state, db.auth_user.id
                )
                if len(reviewersListSel) == 0:
                    redirect(URL(c="recommender", f="reviewers", vars=dict(recommId=recommId)))
                else:
                    print("Bug (reviewersListSel) : " + reviewersListSel)
                    session.flash = T("Article no more available", lazy=False)
                    redirect(URL(c="recommender", f="recommendations", vars=dict(articleId=articleId)))
            else:
                print("Bug (lastRecomm) : " + lastRecomm)
                session.flash = T("Article no more available", lazy=False)
                redirect(URL(c="recommender", f="recommendations", vars=dict(articleId=articleId)))
        else:
            print("Bug (articleStatus) : " + article.status)
            session.flash = T("Article no more available", lazy=False)
            redirect(URL(c="recommender", f="recommendations", vars=dict(articleId=articleId)))


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender"))
def recommend_article():
    recommId = request.vars["recommId"]
    if recommId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    recomm = db.t_recommendations[recommId]
    if recomm is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    # NOTE: security hole possible by changing manually articleId value: Enforced checkings below.
    if recomm.recommender_id != auth.user_id:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    else:
        # recomm.is_closed=True # No: recomm closed when validated by managers
        recomm.recommendation_state = "Recommended"
        recomm.update_record()
        art = db.t_articles[recomm.article_id]
        art.status = "Pre-recommended"
        art.update_record()
        # db.commit()
        redirect(URL(c="recommender", f="recommendations", vars=dict(articleId=recomm.article_id)))

######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender"))
def reject_article():
    recommId = request.vars["recommId"]
    if recommId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    recomm = db.t_recommendations[recommId]
    if recomm is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    # NOTE: security hole possible by changing manually articleId value: Enforced checkings below.
    if recomm.recommender_id != auth.user_id:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    else:
        recomm.is_closed = True
        recomm.recommendation_state = "Rejected"
        recomm.update_record()
        art = db.t_articles[recomm.article_id]
        art.status = "Rejected"
        art.update_record()
        db.commit()
        redirect(URL("my_recommendations", vars=dict(pressReviews=False)))


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender"))
def revise_article():
    recommId = request.vars["recommId"]
    if recommId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    recomm = db.t_recommendations[recommId]
    if recomm is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    # NOTE: security hole possible by changing manually articleId value: Enforced checkings below.
    if recomm.recommender_id != auth.user_id:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    else:
        # Do not close recommendation due to reply
        art = db.t_articles[recomm.article_id]
        art.status = "Awaiting revision"
        art.update_record()
        recomm.recommendation_state = "Awaiting revision"
        recomm.update_record()
        db.commit()
        redirect(URL("my_recommendations", vars=dict(pressReviews=False)))


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender"))
def decline_new_article_to_recommend():
    articleId = request.vars["articleId"]
    if articleId is not None:
        # NOTE: No security hole as only logged user can be deleted
        sug_rec = db((db.t_suggested_recommenders.article_id == articleId) & (db.t_suggested_recommenders.suggested_recommender_id == auth.user_id)).select().first()
        if sug_rec is not None:
            sug_rec.declined = True
            sug_rec.update_record()
            db.commit()
            
            emailing.delete_reminder_for_one_suggested_recommender(db, "#ReminderSuggestedRecommenderInvitation", articleId, auth.user_id)

            session.flash = T("Suggestion declined")
    redirect(URL(c="recommender", f="my_awaiting_articles"))


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def suggest_review_to():
    reviewerId = request.vars["reviewerId"]
    new_round = request.vars["new_round"]
    new_stage = request.vars["new_stage"]
    reg_user = request.vars["regUser"]

    if reviewerId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    recommId = request.vars["recommId"]
    if recommId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    recomm = db.t_recommendations[recommId]
    if recomm is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    # NOTE: security hole possible by changing manually articleId value: Enforced checkings below.
    if recomm.recommender_id != auth.user_id and not (auth.has_membership(role="manager")):
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    else:
        redirect(URL(c="recommender", f="email_for_registered_reviewer", vars=dict(recommId=recommId, reviewerId=reviewerId, new_round=new_round, new_stage=new_stage, regUser=reg_user)))


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender"))
def suggest_collaboration_to():
    reviewerId = request.vars["reviewerId"]
    if reviewerId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    recommId = request.vars["recommId"]
    if recommId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    recomm = db.t_recommendations[recommId]
    if recomm is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    # NOTE: security hole possible by changing manually articleId value: Enforced checkings below.
    if recomm.recommender_id != auth.user_id:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    else:
        db.t_press_reviews.update_or_insert(recommendation_id=recommId, contributor_id=reviewerId)
        redirect(URL("my_recommendations", vars=dict(pressReviews=True)))


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def del_reviewer():
    reviewId = request.vars["reviewId"]
    if reviewId:
        if db((db.t_reviews.id == reviewId) & (db.t_recommendations.id == db.t_reviews.recommendation_id) & (db.t_recommendations.recommender_id == auth.user_id)).count() > 0:
            db((db.t_reviews.id == reviewId)).delete()
    redirect(request.env.http_referer)


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def del_reviewer_with_confirmation():
    response.view = "default/myLayout.html"

    reviewId = request.vars["reviewId"]
    rediectUrl = request.vars["rediectUrl"]

    if reviewId and rediectUrl: 
        review = db(db.t_reviews.id == reviewId).select().last()
        reviewer = db(db.auth_user.id == review.reviewer_id).select().last()
        
        if review.review_state != "Awaiting response":
            redirect(request.env.http_referer)
            session.flas(T("Unauthorized"), lazy=False)
        # Show reviewer's cedentials
        if reviewer is not None:
            content = DIV(
                P(
                    B(T("Are you sure you want to decline this invitation in the name of ")),
                    B(reviewer.first_name),
                    " ",
                    B(reviewer.last_name),
                    " (",
                    I(reviewer.email),
                    ") ",
                    B("?"),
                    _style="text-align: center; font-size: 16px"
                )
            )
        else: 
            content = DIV(
                P(
                    B(T("Are you sure to decline this review of this ")),
                    I(T("[unknown user] ?")),
                    _style="text-align: center; font-size: 16px"
                )
            )

        form = FORM.confirm(T('Decline this review'), {'Back': rediectUrl})
        
        if form.accepted:
            if auth.has_membership(role="manager"):
                if db((db.t_reviews.id == reviewId) & (db.t_recommendations.id == db.t_reviews.recommendation_id)).count() > 0:
                    review.review_state = "Declined manually"
                    review.update_record()
            else:
                if db((db.t_reviews.id == reviewId) & (db.t_recommendations.id == db.t_reviews.recommendation_id) & (db.t_recommendations.recommender_id == auth.user_id)).count() > 0:
                    review.review_state = "Declined manually"
                    review.update_record()

            redirect(rediectUrl)

    
        return dict(content=content, form=DIV(form, _class="confirmation-form"))

    redirect(request.env.http_referer)



######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender"))
def process_opinion():
    if "recommender_opinion" in request.vars and "recommId" in request.vars:
        ro = request.vars["recommender_opinion"]
        rId = request.vars["recommId"]
        if ro == "do_recommend":
            redirect(URL(c="recommender_actions", f="recommend_article", vars=dict(recommId=rId)))
        elif ro == "do_revise":
            redirect(URL(c="recommender_actions", f="revise_article", vars=dict(recommId=rId)))
        elif ro == "do_reject":
            redirect(URL(c="recommender_actions", f="reject_article", vars=dict(recommId=rId)))
    redirect(URL("my_recommendations", vars=dict(pressReviews=False)))


###############################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def add_recommender_as_reviewer():
    recommId = request.vars["recommId"]
    recomm = db.t_recommendations[recommId]
    if (recomm.recommender_id != auth.user_id) and not (auth.has_membership(role="manager")):
        session.flash = auth.not_authorized()
    else:
        # check if review previously cancelled, then reopen
        reviews = db((db.t_reviews.reviewer_id == recomm.recommender_id) & (db.t_reviews.recommendation_id == recommId)).select()
        if len(reviews) > 0:
            for review in reviews:
                review.update_record(review_state="Awaiting review")
                db.commit()
        else:  # create review
            rid = db.t_reviews.validate_and_insert(
                recommendation_id=recommId, reviewer_id=recomm.recommender_id, no_conflict_of_interest=recomm.no_conflict_of_interest, review_state="Awaiting review"
            )
    redirect(request.env.http_referer)


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def cancel_recommender_as_reviewer():
    recommId = request.vars["recommId"]
    if recommId:
        recomm = db.t_recommendations[recommId]
        if (recomm.recommender_id != auth.user_id) and not (auth.has_membership(role="manager")):
            session.flash = auth.not_authorized()
        else:
            reviews = db((db.t_reviews.reviewer_id == recomm.recommender_id) & (db.t_reviews.recommendation_id == recommId)).select()
            for review in reviews:
                if (recomm.recommender_id == auth.user_id) or (auth.has_membership(role="manager")):
                    review.update_record(review_state="Cancelled")
                    db.commit()
                else:
                    session.flash = auth.not_authorized()
    else:
        session.flash = auth.not_authorized()
    redirect(request.env.http_referer)


######################################################################################################################################################################
def check_accept_decline_request():
    if "reviewId" not in request.vars:
        raise HTTP(404, "404: " + T("Unavailable"))
    reviewId = request.vars["reviewId"]
    rev = db.t_reviews[reviewId]
    if rev is None:
        raise HTTP(404, "404: " + T("Unavailable"))

    recomm = db((db.t_recommendations.id == rev["recommendation_id"])).select(db.t_recommendations.ALL).last()
    if auth.has_membership(role="manager"):
        pass
    elif recomm.recommender_id != auth.user_id:
        raise HTTP(404, "404: " + T("Unavailable"))

    if rev["review_state"] != "Willing to review":
        session.flash = T("Review state has been changed")
        redirect_to_recommendations(recomm)

    return rev, recomm


def redirect_to_recommendations(recomm):
    controller = "manager" if auth.has_membership(role="manager") else "recommender"

    redirect(URL(c=controller, f="recommendations", vars=dict(articleId=recomm["article_id"])))


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def accept_review_request():
    rev, recomm = check_accept_decline_request()

    # db(db.t_reviews.id==reviewId).delete()
    rev.review_state = "Awaiting review"
    rev.update_record()
    # email to recommender sent at database level
    redirect_to_recommendations(recomm)


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def decline_review_request():
    rev, recomm = check_accept_decline_request()

    # db(db.t_reviews.id==reviewId).delete()
    rev.review_state = "Declined by recommender"
    rev.update_record()
    # email to recommender sent at database level
    redirect_to_recommendations(recomm)


######################################################################################################################################################################
def make_preprint_searching_for_reviewers():
    recommId = request.vars["recommId"]
    if recommId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)

    recomm = db.t_recommendations[recommId]
    if recomm is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)

    if recomm.recommender_id != auth.user_id and not recomm.is_closed and not (auth.has_membership(role="administrator") or auth.has_membership(role="manager")):
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    else:
        art = db.t_articles[recomm.article_id]

        art.is_searching_reviewers = True
        art.update_record()
        db.commit()
        session.flash = 'Preprint now appear in the "In need of reviewers" list'
        redirect(request.env.http_referer)


######################################################################################################################################################################
def make_preprint_not_searching_for_reviewers():
    recommId = request.vars["recommId"]
    if recommId is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)

    recomm = db.t_recommendations[recommId]
    if recomm is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)

    if recomm.recommender_id != auth.user_id and not recomm.is_closed and not (auth.has_membership(role="administrator") or auth.has_membership(role="manager")):
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    else:
        art = db.t_articles[recomm.article_id]
        art.is_searching_reviewers = False
        art.update_record()
        db.commit()
        session.flash = 'Preprint is removed from the "In need of reviewers" list'
        redirect(request.env.http_referer)


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def delete_recommendation_file():
    recommId = request.vars["recommId"]
    recomm = db.t_recommendations[recommId]
    art = db.t_articles[recomm.article_id]
    isPress = None

    amICoRecommender = db((db.t_press_reviews.recommendation_id == recomm.id) & (db.t_press_reviews.contributor_id == auth.user_id)).count() > 0

    if (recomm.recommender_id != auth.user_id) and not amICoRecommender and not (auth.has_membership(role="manager")):
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    elif art.status not in ("Under consideration", "Pre-recommended", "Pre-revision", "Pre-cancelled", "Pre-recommended-private"):
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)

    if not ("recommId" in request.vars):
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)

    if not ("fileType" in request.vars):
        session.flash = T("Unavailable")
        redirect(request.env.http_referer)
    else:
        print(request.vars.fileType)
        if request.vars.fileType == "reply_pdf":
            recomm.reply_pdf = None
            recomm.reply_pdf_data = None
            recomm.update_record()
        elif request.vars.fileType == "track_change":
            recomm.track_change = None
            recomm.track_change_data = None
            recomm.update_record()
        elif request.vars.fileType == "recommender_file":
            recomm.recommender_file = None
            recomm.recommender_file_data = None
            recomm.update_record()
        else:
            session.flash = T("Unavailable")
            redirect(request.env.http_referer)

    session.flash = T("File successfully deleted")
    
    redirect(request.env.http_referer)


######################################################################################################################################################################
@auth.requires(auth.has_membership(role="recommender") or auth.has_membership(role="manager"))
def do_end_scheduled_submission():
    if not ("articleId" in request.vars):
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    articleId = request.vars["articleId"]
    art = db.t_articles[articleId]
    if art is None:
        session.flash = auth.not_authorized()
        redirect(request.env.http_referer)
    if art.status == "Scheduled submission under consideration":
        art.status = "Under consideration"
        art.update_record()

        # Create reminder for reviewers
        awaitingReviews = db(
            (db.t_reviews.recommendation_id == db.t_recommendations.id)
            & (db.t_recommendations.article_id == db.t_articles.id)
            & (db.t_articles.id == articleId)
            & (db.t_reviews.review_state == "Awaiting review")
        ).select()
        for review in awaitingReviews:
            emailing.create_reminder_for_reviewer_review_soon_due(session, auth, db, review["t_reviews.id"])
            emailing.create_reminder_for_reviewer_review_due(session, auth, db, review["t_reviews.id"])
            emailing.create_reminder_for_reviewer_review_over_due(session, auth, db, review["t_reviews.id"])

        session.flash = T("Submission now available to reviewers")

    redirect(URL(c="recommender", f="recommendations", vars=dict(articleId=articleId), user_signature=True))
