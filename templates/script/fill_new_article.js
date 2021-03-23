jQuery(document).ready(function() {
  if (jQuery("#t_articles_picture_rights_ok").prop("checked")) {
    jQuery("#t_articles_uploaded_picture").prop("disabled", false);
  } else {
    jQuery("#t_articles_uploaded_picture").prop("disabled", true);
  }

  if (jQuery("#t_articles_already_published").prop("checked")) {
    jQuery("#t_articles_article_source__row").show();
  } else {
    jQuery("#t_articles_article_source__row").hide();
    jQuery(":submit").prop("disabled", true);
  }

  if (jQuery("#t_articles_already_published").length)
    jQuery(":submit").prop("disabled", false);

  if (jQuery("#t_articles_is_not_reviewed_elsewhere").prop("checked")) {
    jQuery("#t_articles_parallel_submission").prop("disabled", true);
  }

  if (
    (jQuery("#t_articles_is_not_reviewed_elsewhere").prop("checked") |
      jQuery("#t_articles_parallel_submission").prop("checked")) &
    jQuery("#t_articles_i_am_an_author").prop("checked")
  ) {
    jQuery(":submit").prop("disabled", false);
  } else {
    jQuery(":submit").prop("disabled", true);
  }

  jQuery("#t_articles_picture_rights_ok").change(function() {
    if (jQuery("#t_articles_picture_rights_ok").prop("checked")) {
      jQuery("#t_articles_uploaded_picture").prop("disabled", false);
    } else {
      jQuery("#t_articles_uploaded_picture").prop("disabled", true);
      jQuery("#t_articles_uploaded_picture").val("");
    }
  });

  jQuery("#t_articles_already_published").change(function() {
    if (jQuery("#t_articles_already_published").prop("checked")) {
      jQuery("#t_articles_article_source__row").show();
    } else {
      jQuery("#t_articles_article_source__row").hide();
    }
  });

  jQuery("#t_articles_is_not_reviewed_elsewhere").change(function() {
    if (jQuery("#t_articles_is_not_reviewed_elsewhere").prop("checked")) {
      jQuery("#t_articles_parallel_submission").prop("checked", false);
      jQuery("#t_articles_parallel_submission").prop("disabled", true);
    } else {
      jQuery("#t_articles_parallel_submission").prop("disabled", false);
    }
    if (
      (jQuery("#t_articles_is_not_reviewed_elsewhere").prop("checked") |
        jQuery("#t_articles_parallel_submission").prop("checked")) &
      jQuery("#t_articles_i_am_an_author").prop("checked")
    ) {
      jQuery(":submit").prop("disabled", false);
    } else {
      jQuery(":submit").prop("disabled", true);
    }
  });
  jQuery("#t_articles_i_am_an_author").change(function() {
    if (
      (jQuery("#t_articles_is_not_reviewed_elsewhere").prop("checked") |
        jQuery("#t_articles_parallel_submission").prop("checked")) &
      jQuery("#t_articles_i_am_an_author").prop("checked")
    ) {
      jQuery(":submit").prop("disabled", false);
    } else {
      jQuery(":submit").prop("disabled", true);
    }
  });
  jQuery("#t_articles_parallel_submission").change(function() {
    if (jQuery("#t_articles_parallel_submission").prop("checked")) {
      jQuery("#t_articles_is_not_reviewed_elsewhere").prop("checked", false);
      jQuery("#t_articles_is_not_reviewed_elsewhere").prop("disabled", true);
    } else {
      jQuery("#t_articles_is_not_reviewed_elsewhere").prop("disabled", false);
    }
    if (
      (jQuery("#t_articles_is_not_reviewed_elsewhere").prop("checked") |
        jQuery("#t_articles_parallel_submission").prop("checked")) &
      jQuery("#t_articles_i_am_an_author").prop("checked")
    ) {
      jQuery(":submit").prop("disabled", false);
    } else {
      jQuery(":submit").prop("disabled", true);
    }
  });
});

// Crossref API
function insertAfter(referenceNode, newNode) {
  referenceNode.parentNode.insertBefore(newNode, referenceNode.nextSibling);
}

var doi_button_container = document.createElement("div");
doi_button_container.classList = "pci2-flex-row pci2-align-items-center";
doi_button_container.style = "margin: 5px 0 0";

var button = document.createElement("a");
button.innerHTML = "Complete form automatically";
button.classList = "btn btn-default";
button.style = "margin: 0";
button.onclick = getCrossrefDatas;

var error_message = document.createElement("span");
error_message.style = "margin-left: 10px; font-weight: bold";

doi_button_container.appendChild(button);
doi_button_container.appendChild(error_message);

var div = document.getElementById("t_articles_doi");
insertAfter(div, doi_button_container);

var prevent_double_submit = false;

function getCrossrefDatas() {
  if (!prevent_double_submit) {
    prevent_double_submit = true;
    button.classList = "btn btn-default disabled";

    error_message.innerHTML =
      '<div class="pci2-flex-row pci2-align-items-center"><i class="glyphicon glyphicon-refresh icon-rotating" style="color: #ffbf00; font-size: 20px; margin-right:5px"></i> <span>Waiting for Crossref API...</span></div>';

    console.log("toto");
    var doi = document.getElementById("t_articles_doi").value;
    httpRequest = new XMLHttpRequest();

    httpRequest.onreadystatechange = alertContents;
    httpRequest.open("GET", "https://api.crossref.org/works/" + doi, true);
    httpRequest.send();
  }
}

function alertContents() {
  if (httpRequest.readyState === XMLHttpRequest.DONE) {
    prevent_double_submit = false;
    button.classList = "btn btn-default";

    if (httpRequest.status === 200) {
      fillFormFields(httpRequest.responseText);
      error_message.innerText = "Some fields have been auto-filled";
      error_message.classList = "success-text";
    } else {
      error_message.innerText = "Error : doi not found";
      error_message.classList = "danger-text";
    }
  }
}

function fillFormFields(data) {
  data_json = JSON.parse(data);
  console.log(data_json);

  // title
  document.getElementById("t_articles_title").value =
    data_json.message.title[0];

  // authors
  var authors = "";
  var i = 0;
  data_json.message.author.forEach(author_data => {
    authors += author_data.given + " " + author_data.family;

    i++;
    if (data_json.message.author[i]) {
      authors += ", ";
    }
  });
  document.getElementById("t_articles_authors").value = authors;

  // abstract
  if (data_json.message.abstract) {
    document.getElementById(
      "t_articles_abstract_ifr"
    ).contentDocument.body.innerHTML = data_json.message.abstract;
  } else {
    document.getElementById(
      "t_articles_abstract_ifr"
    ).contentDocument.body.innerHTML = "";
  }
}

// // PCI RR
// let elemPciRR = document.querySelector(
//   "#t_articles_art_stage_1_id option[value='']"
// );
// if (elemPciRR) {
//   document.querySelector(
//     "#t_articles_art_stage_1_id option[value='']"
//   ).innerHTML = "This is a stage 1 submission";
// }

// // Scheduled submission
// let elemScheduledSubmission = document.querySelector(
//   "#t_articles_scheduled_submission_date__row"
// );

// if (elemScheduledSubmission) {
//   elemScheduledSubmission.style.display = "none";

//   let checkboxFormGroup = document.createElement("div");
//   checkboxFormGroup.classList = "form-group";
//   elemScheduledSubmission.before(checkboxFormGroup);

//   let checkboxContainer = document.createElement("div");
//   checkboxContainer.classList = "col-sm-3";
//   checkboxFormGroup.appendChild(checkboxContainer);

//   let checkboxContainer2 = document.createElement("div");
//   checkboxContainer2.classList = "checkbox";
//   checkboxContainer.appendChild(checkboxContainer2);

//   let checkboxLabel = document.createElement("label");
//   checkboxContainer2.appendChild(checkboxLabel);

//   let checkboxInput = document.createElement("input");
//   checkboxInput.setAttribute("type", "checkbox");
//   checkboxInput.id = "checkbox-scheduled-submission";
//   checkboxInput.onchange = toggleScheduledSubmission;
//   checkboxLabel.appendChild(checkboxInput);

//   checkboxText = document.createTextNode(
//     "This is a scheduled submission (no doi yet)"
//   );
//   checkboxLabel.appendChild(checkboxText);
// }

// function toggleScheduledSubmission() {
//   let scheduledSubmissionRow = document.querySelector(
//     "#t_articles_scheduled_submission_date__row"
//   );
//   let scheduledSubmissionInput = document.querySelector(
//     "#t_articles_scheduled_submission_date"
//   );

//   let doiRow = document.querySelector("#t_articles_doi__row");
//   let doiInput = document.querySelector("#t_articles_doi");

//   let msVersionRow = document.querySelector("#t_articles_ms_version__row");
//   let msVersionInput = document.querySelector("#t_articles_ms_version");

//   let elem = document.querySelector("#checkbox-scheduled-submission");

//   // if scheduled subbmission is checked
//   if (elem.checked) {
//     doiRow.style.display = "none";
//     msVersionRow.style.display = "none";
//     msVersionInput.value = "";
//     doiInput.value = "";
//     scheduledSubmissionRow.style.display = "flex";
//   } else {
//     scheduledSubmissionRow.style.display = "none";
//     scheduledSubmissionInput.value = "";
//     doiRow.style.display = "flex";
//     msVersionRow.style.display = "flex";
//   }
// }
