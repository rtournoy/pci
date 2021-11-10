from conftest import config, select
from conftest import login, logout

import time


users = config.users


from argparse import Namespace

articleTitle = "Article Title [%s]" % time.asctime()

submitter = Namespace(
    firstname="Submitter",
    lastname="Dude",
    )
recommender = Namespace(
    firstname="Recommender",
    lastname="Dude",
    )
data = Namespace(
    doi = "DOI",
    abstract = "Abstract",
    keywords = "Keywords",
    cover_letter = "Cover letter",
    )

class Test_user_submits_preprint:

 def test_login_as_user(_):
    login(users.user)

 def test_initiate_submit_preprint(_):
    select(".btn-success", "Submit a preprint".upper()).click()
    select(".btn-success", "Submit your preprint".upper()).click()

 def test_submit_submission_form(_):
    select("#t_articles_title").send_keys(articleTitle)
    select("#t_articles_authors").send_keys(submitter.firstname + " " + submitter.lastname)
    select("#t_articles_doi").send_keys(data.doi)
    #select("#t_articles_abstract").send_keys(data.abstract)
    with select("#t_articles_abstract_ifr").frame():
        select("body").send_keys(data.abstract)
    select("#t_articles_keywords").send_keys(data.keywords)
    #select("#t_articles_cover_letter").send_keys(data.cover_letter)
    with select("#t_articles_cover_letter_ifr").frame():
        select("body").send_keys(data.cover_letter)

    select('input[name="thematics"]')[0].click()
    select("#t_articles_i_am_an_author").click()
    select("#t_articles_is_not_reviewed_elsewhere").click()
    select("input[type=submit]").click()

    select(".w2p_flash", "Article submitted").wait_clickable()

 def test_search_and_suggest_recommender(_):
    select("a", "Suggest recommenders".upper()).click()
    select('input[name="qyKeywords"]').clear()
    select('input[name="qyKeywords"]').send_keys(recommender.firstname)
    select(".pci2-search-button").click()
    select("a", "Suggest as recommender".upper()).click()

 def test_mail_sent_to_recommender(_):
    select(".w2p_flash").contains("Suggested recommender")
    select("a", "Done".upper()).click()

 def test_complete_submission(_):
    select("a", "Complete your submission".upper()).click()

    select(".pci-status", "SUBMISSION PENDING VALIDATION")
    """
      select(".pci-status")
        .first()
        .should("contain", "SUBMISSION PENDING VALIDATION");
    """

 def test_logout_user(_):
    logout(users.user)


class Test_manager_validates_submission:

 def test_login_as_manager(_):
    login(users.manager)

 def test_article_shown_in_pending_validation(_):
    select(".dropdown-toggle span", "For managers").click()
    select(".dropdown-menu span", contains="Pending validation").click()
    select("tr", contains=articleTitle)
    select(".pci-status", "SUBMISSION PENDING VALIDATION")
    """
        .first()
        .should("exist");
    """

 def test_validate_submission(_):
    #select("a", "View / Edit").first().click()  # select(css, text/contains=xxx) should return a list-ish
    select("a", "View / Edit".upper()).click()
    select(".btn-success", "Validate this submission".upper()).click()
    select(".w2p_flash", "Request now available to recommenders").wait_clickable()

 """
    it("Should show article status 'PREPRINT REQUIRING A RECOMMENDER'", () => {
      select(".dropdown-toggle", "For managers").click();
      select("a", "All article").click();

      select("tr", articleTitle).should("exist");
      select(".pci-status", "PREPRINT REQUIRING A RECOMMENDER")
        .first()
        .should("exist");

    it("Should no longer show article in 'Pending validation(s)' page", () => {
      select(".dropdown-toggle", "For managers").click();
      select("a", "Pending validation").click();

      select("tr", articleTitle).should("not.exist");
 """

 def test_logout_manager(_):
    logout(users.manager)


class _Test_recommender_handles_preprint:

 def test_login_as_recommender(_):
    login(users.recommender)

 """

    it("Should show 'Request(s) to handle a preprint' enhanced menu", () => {
      select(".dropdown-toggle", "For recommenders").click();
      select("a", "Request(s) to handle a preprint").click();

    it("Should show article in 'Request(s) to handle a preprint' page", () => {
      select("tr", articleTitle).should("exist");
      select(".pci-status", "PREPRINT REQUIRING A RECOMMENDER").should("exist");

    it("Should accept to recommend the preprint", () => {
      select("a", "View").first().click();
      select(".btn-success.pci-recommender").click();

      select("input[type=submit]").should("have.attr", "disabled");
      select("input[type=checkbox]").each(($el) => {
        $el.click();
      });
      select("input[type=submit]").should("not.have.attr", "disabled");
      select("input[type=submit]").click();

    it("=> mail sent to manager, submitter and recommender", () => {
      cy.wait(500);
      select(".w2p_flash", "e-mail sent to manager").should("exist");
      select(".w2p_flash", "e-mail sent to submitter").should("exist");
      select(".w2p_flash", "e-mail sent to " + recommender.firstname).should("exist");

    it("Should search for reviewer (developer user)", () => {
      select(".btn", "Choose a reviewer from the PCI Evol Biol DEV database").click();

      select('input[name="qyKeywords"]').send_keys(reviewer.firstname);
      select(".pci2-search-button").click();

      select("a", "Prepare an invitation").should("exist");

    it("Should invite reviewer", () => {
      select("a", "Prepare an invitation").click();
      select("input[type=submit]").click();

    it("=> mail sent to reviewer", () => {
      cy.wait(500);
      select(".w2p_flash", "e-mail sent to " + reviewer.firstname).should("exist");
      select("a", "Done").click();

    it("Should show article in list of articles", () => {
      select("tr", articleTitle).should("exist");


  describe("Recommender :  invite external un-registered reviewer", () => {

    it("Should show article in recommender dashboard", () => {
      select(".dropdown-toggle", "For recommenders").click();
      select("a", "Preprint(s) you are handling").click();
      select(".doi_url", data.doi).should("exist");

    it("Should invite reviewer outside PCI database", () => {
      select(".btn", "Invite a reviewer").first().click();
      select(".btn", "Choose a reviewer outside PCI Evol Biol DEV database").click();

      select("#no_table_reviewer_first_name").send_keys("Titi");
      select("#no_table_reviewer_last_name").send_keys("Toto");
      select("#no_table_reviewer_email").send_keys("ratalatapouet@toto.com");

      select("input[type=submit]").click();

    it("=> mail sent to reviewer outside PCI db", () => {
      cy.wait(500);
      select(".w2p_flash", "e-mail sent to Titi Toto").should("exist");
 """

 def test_logout_recommender(_):
    logout(users.recommender)
