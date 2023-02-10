from gluon.html import TAG
from app_modules.common_small_html import md_to_html


class pci:
    host = db.cfg.host
    issn = db.cfg.issn
    url = f"https://{host}.peercommunityin.org"
    doi = f"10.24072/pci.{host}"
    long_name = db.conf.get("app.description")
    short_name = db.conf.get("app.longname")
    email = db.conf.get("contacts.contact")

class crossref:
    version = "4.3.7"
    base = "http://www.crossref.org/schema"
    xsd = f"{base}/crossref{version}.xsd"


def mk_recomm_description(recomm, article):
    year = recomm.last_change.strftime("%Y")
    title = md_to_html(article.title).flatten()
    return " ".join([
        "A recommendation of:",
        f"{article.authors}",
        f"({year})",
        f"{title}.",
        f"{article.preprint_server},",
        f"ver.{article.ms_version}",
        f"peer-reviewed and recommended by {pci.short_name}",
        f"{article.doi}",
        #article.article_source,
    ])


def mk_affiliation(user):
    _ = user
    return f"{_.laboratory}, {_.institution} – {_.city}, {_.country}"


def get_identifier_type(article):
    article_server = (article.preprint_server or "").lower()
    source_has_doi = "biorxiv zenodo osf arxiv".split()
    for doi_src in source_has_doi:
        if doi_src in article_server:
            return "doi"

    return "other"


def crossref_xml(recomm):
    article = db.t_articles[recomm.article_id]

    recomm_url = f"{pci.url}/articles/rec?id={recomm.id}"
    recomm_doi = f"{pci.doi}.1"+str(article.id).zfill(5)
    recomm_date = recomm.validation_timestamp.date()
    recomm_title = recomm.recommendation_title
    recomm_description_text = mk_recomm_description(recomm, article)
    article_doi = article.doi

    recommender = db.auth_user[recomm.recommender_id]
    co_recommenders = []

    for user in [recommender] + co_recommenders:
        user.affiliation = mk_affiliation(user)

    interwork_type = get_identifier_type(article)
    interwork_ref = article_doi
    item_number = recomm_doi[-6:]

    timestamp = recomm.last_change.now().strftime("%Y%m%d%H%M%S%f")[:-3]
    batch_id = f"pci={pci.host}:rec={recomm.id}"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <doi_batch
        xmlns="{crossref.base}/{crossref.version}"
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="
            {crossref.base}/{crossref.version}
            {crossref.xsd}"
        version="{crossref.version}">
    <head>
        <doi_batch_id>{batch_id}</doi_batch_id>
        <timestamp>{timestamp}</timestamp>
        <depositor>
            <depositor_name>peercom</depositor_name>
            <email_address>{pci.email}</email_address>
        </depositor>
        <registrant>Peer Community In</registrant>
    </head>
    <body>
    <journal>

    <journal_metadata language="en">
        <full_title>{TAG(pci.long_name)}</full_title>
        <abbrev_title>{TAG(pci.short_name)}</abbrev_title>
        """ + (f"""
        <issn media_type='electronic'>{pci.issn}</issn>
        """ if pci.issn else "") + f"""
        <doi_data>
            <doi>{pci.doi}</doi>
            <resource>{pci.url}</resource>
        </doi_data>
    </journal_metadata>

    <journal_issue>
        <publication_date media_type='online'>
            <month>{recomm_date.month}</month>
            <day>{recomm_date.day}</day>
            <year>{recomm_date.year}</year>
        </publication_date>
    </journal_issue>

    <journal_article publication_type='full_text'>

    <titles>
        <title>
            {TAG(recomm_title)}
        </title>
    </titles>

    <contributors>
        <person_name sequence='first' contributor_role='author'>
            <given_name>{TAG(recommender.first_name)}</given_name>
            <surname>{TAG(recommender.last_name)}</surname>
            <affiliation>{TAG(recommender.affiliation)}</affiliation>
        </person_name>
        """ + "\n".join([f"""
        <person_name sequence='additional' contributor_role='author'>
            <given_name>{TAG(co_recommender.first_name)}</given_name>
            <surname>{TAG(co_recommender.last_name)}</surname>
            <affiliation>{TAG(co_recommender.affiliation)}</affiliation>
        </person_name>
        """ for co_recommender in co_recommenders ]) + f"""
    </contributors>

    <publication_date media_type='online'>
        <month>{recomm_date.month}</month>
        <day>{recomm_date.day}</day>
        <year>{recomm_date.year}</year>
    </publication_date>

    <publisher_item>
        <item_number item_number_type="article_number">{item_number}</item_number>
    </publisher_item>

    <program xmlns="http://www.crossref.org/AccessIndicators.xsd">
        <free_to_read/>
        <license_ref applies_to="vor" start_date="{recomm_date.isoformat()}">
            https://creativecommons.org/licenses/by/4.0/
        </license_ref>
    </program>

    <program xmlns="http://www.crossref.org/relations.xsd">
    <related_item>
        <description>
            {TAG(recomm_description_text)}
        </description>
        <inter_work_relation
            relationship-type="isReviewOf"
            identifier-type="{interwork_type}">
            {interwork_ref}
        </inter_work_relation>
    </related_item>
    </program>

    <doi_data>
        <doi>{recomm_doi}</doi>
        <resource>
            {recomm_url}
        </resource>

        <collection property="crawler-based">
        <item crawler="iParadigms">
        <resource>
            {recomm_url}
        </resource>
        </item>
        </collection>

        <collection property="text-mining">
        <item>
        <resource content_version="vor">
            {recomm_url}
        </resource>
        </item>
        </collection>
    </doi_data>

    </journal_article>
    </journal>
    </body>
    </doi_batch>
    """
