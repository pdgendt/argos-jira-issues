#!/usr/bin/env python3
import base64
import json
import os
import sys
from datetime import datetime

import gi
import requests
from jira import JIRA

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # isort:skip


# LOAD CONFIGURATION

os.chdir(os.path.dirname(os.path.realpath(__file__)))

# TODO: error handling, file creation
with open(".jira_credentials.json", "r") as f:
    credentials = json.load(f)
with open(".jira_reviewers.json", "r") as f:
    reviewers = json.load(f)

try:
    with open(".jira_progress.json", "r") as f:
        progress = json.load(f)
except FileNotFoundError:
    progress = {}


jira = JIRA(
    credentials["host"], basic_auth=(credentials["username"], credentials["password"])
)


# HELPER FUNCTIONS
def startTracking(issue):
    global progress

    # Stop tracking other issues
    for issueToStop in list(progress.keys()):
        stopTracking(issueToStop)

    with open(".jira_progress.json", "w+") as f:
        progress[issue] = datetime.now().timestamp()
        json.dump(progress, f)


def stopTracking(issue):
    global progress

    if issue in progress.keys():
        timeStarted = datetime.fromtimestamp(progress[issue])
        timeNow = datetime.now()
        diffMinutes = (timeNow - timeStarted).seconds / 60
        if diffMinutes >= 1:
            jira.add_worklog(
                issue,
                timeSpent=str(diffMinutes) + "m",
                comment="Auto-logged by JIRA Issue Manager",
            )

        with open(".jira_progress.json", "w+") as f:
            del progress[issue]
            json.dump(progress, f)


def getAsBase64(url):
    return base64.b64encode(requests.get(url).content).decode("utf-8")


def getIssueWithStatus(status):
    return jira.search_issues(
        'status = "'
        + status
        + '" AND resolution = Unresolved AND assignee in (currentUser())'
    )


def addSeparator():
    print("---")


def addMenuItem(text, options=None):
    optionsText = ""
    if options:
        optionsText += "|"

        # Override defaults
        if "bash" in options:
            if "refresh" not in options:
                options["refresh"] = "true"
            if "terminal" not in options:
                options["terminal"] = "false"

        for key in options:
            optionsText += "%s=%s " % (key, options[key])
    print(text + optionsText)


def addSubMenuItem(text, options):
    addMenuItem("--" + text, options)


def addLinkToIssue(issue, subMenu=False):
    link = "%s/projects/%s/issues/%s" % (
        credentials["host"],
        issue.key.split("-")[0],
        issue.key,
    )
    addMenuItem(
        "%sShow issue in browser..." % ("", "--")[subMenu],
        {"href": link, "iconName": "application-exit"},
    )


def canTransitionTo(issue, transition):
    matchingTransitions = [
        (t["id"], t["name"]) for t in jira.transitions(issue) if t["name"] == transition
    ]

    return len(matchingTransitions) > 0


# COMMAND LINE INVOCATION

if len(sys.argv) > 1:
    if len(sys.argv) == 2:
        if str(sys.argv[1]) == "users":
            print("Username\t(Display Name)")
            print("--------\t--------------")
            for user in jira.search_users("", maxResults=150):
                print(user.key + "\t(%s)" % user.displayName)

        if str(sys.argv[1]) == "custom":

            window = Gtk.Window(title="Track other issue")
            window.set_border_width(20)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            window.add(vbox)

            label = Gtk.Label(label="Enter issue key:")
            vbox.pack_start(label, True, True, 0)

            text = Gtk.Entry()
            vbox.pack_start(text, True, True, 0)

            button = Gtk.Button.new_with_label("Start tracking time")
            vbox.pack_start(button, True, True, 0)

            def start_progress(button):
                startTracking(text.get_text())
                exit(0)

            button.connect("clicked", start_progress)
            text.connect("activate", start_progress)

            window.set_position(Gtk.WindowPosition.CENTER)
            window.show_all()
            window.connect("destroy", Gtk.main_quit)
            Gtk.main()

    elif len(sys.argv) >= 4 and str(sys.argv[1]) == "transition":
        issue = sys.argv[2]
        transition = sys.argv[3]

        if transition == "Start progress":
            for issueToStop in list(progress.keys()):
                if canTransitionTo(issueToStop, "Stop progress"):
                    jira.transition_issue(issueToStop, "Stop progress")

            startTracking(issue)

        elif transition == "Resolved" or transition == "Stop progress":
            stopTracking(issue)

        if canTransitionTo(issue, transition):
            if transition == "Resolved":
                jira.transition_issue(issue, transition, assignee={"name": sys.argv[4]})
            else:
                jira.transition_issue(issue, transition)

    exit(0)

# MAIN PROGRAM START

trackingIssues = [jira.issue(ticket) for ticket in list(progress.keys())]
ticketList = [
    ticket
    for ticket in getIssueWithStatus("Next") + getIssueWithStatus("In Progress")
    if ticket not in trackingIssues
]

if len(trackingIssues) == 0:
    addMenuItem('💤  <span font_weight="normal">Not working...</span>')

    if len(ticketList) == 0:
        addSeparator()
        addMenuItem('Put issues in "Next" to make them appear in this list')

elif len(trackingIssues) > 1:
    addMenuItem("You can only track one issue!")
    addMenuItem("Something went wrong 🤭")
    addSeparator()

else:
    issue = trackingIssues[0]
    addMenuItem(
        "👨‍💻  "
        + issue.key
        + ' - <span font_weight="normal">'
        + issue.fields.summary
        + "</span>"
    )
    addSeparator()
    addMenuItem("<b>" + issue.fields.summary + "</b>")
    if issue.fields.description:
        addMenuItem(issue.fields.description)

    addMenuItem(
        "Stop progress",
        {
            "bash": "'%s transition %s \"Stop progress\"'" % (sys.argv[0], issue.key),
            "iconName": "media-playback-pause-symbolic",
        },
    )

    if canTransitionTo(issue, "Resolved"):
        addMenuItem(
            "Resolve and reassign for review",
            {"iconName": "document-properties-symbolic"},
        )
        for user in reviewers:
            rawUser = jira.user(user).raw
            addSubMenuItem(
                rawUser["displayName"],
                {
                    "image": getAsBase64(rawUser["avatarUrls"]["16x16"]),
                    "imageWidth": 16,
                    "imageHeight": 16,
                    "bash": "'%s transition %s \"Resolved\" %s'"
                    % (sys.argv[0], issue.key, rawUser["key"]),
                },
            )

    if canTransitionTo(issue, "Select"):
        addMenuItem(
            "Select",
            {
                "iconName": "view-pin-symbolic",
                "bash": "'%s transition %s \"Select\"'" % (sys.argv[0], issue.key),
            },
        )

    addLinkToIssue(issue)

addSeparator()

for issue in ticketList:
    addMenuItem("<b>%s</b>: %s" % (issue.key, issue.fields.summary))
    addSubMenuItem(
        ("Start tracking", "Start progress")[canTransitionTo(issue, "Start progress")],
        {
            "bash": "'%s transition %s \"%s\"'"
            % (sys.argv[0], issue.key, "Start progress"),
            "iconName": "media-playback-start-symbolic",
        },
    )

    if canTransitionTo(issue, "Stop progress"):
        addSubMenuItem(
            "Stop progress",
            {
                "bash": "'%s transition %s \"%s\"'"
                % (sys.argv[0], issue.key, "Stop progress"),
                "iconName": "media-playback-stop-symbolic",
            },
        )
    if canTransitionTo(issue, "Deselect"):
        addSubMenuItem(
            "Deselect",
            {
                "bash": "'%s transition %s \"%s\"'"
                % (sys.argv[0], issue.key, "Deselect"),
                "iconName": "edit-clear-symbolic",
            },
        )

    addLinkToIssue(issue, subMenu=True)

addMenuItem("Track other issue...", {"bash": "'%s custom'" % sys.argv[0]})

addSeparator()

addMenuItem(
    "Open JIRA",
    {
        "href": credentials["host"],
        "image": "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAMZJREFUOI2Vkj0OAUEAhb9IJOKn3PM5gEaCWqOROIIrKPWicAm9hEoidHyaXdaameUl00zevL8MpDEFZjWcKDL1ql6ALEZqJAT6QBvoAuO/7dWNbyRTxATOJQGB+T/vW+rDTwRTxDZ4BO66wKjOOQNWQE89+Y3aLeZ53yWwDggkt8jUS867A4uQQDVFeYNx3rO4bwKnyBZf/6LsXmAHTH5J8epewQHoqMe6LULuhQC/pAi5q25zgXQKda/eqgcYlCoOQxx1/wRTboLP64okfwAAAABJRU5ErkJggg==",
    },
)
addMenuItem("Refresh", {"bash": "", "iconName": "object-rotate-right-symbolic"})
