var api = {};

var flash = function(message, cls) {
	var xclass = 'flash';
	if (cls !== undefined) {
		var xclass = "flash " + cls;
	    }
        $('.flashes-container').empty();
	$('.flashes-container').append($('<div class="' + xclass + '">' + message + '</div>'));
	$('body').scrollTop(0);
};

var generate_embedded_tweets = function() {
	var numtweets = $('.tweet').length;
	var numtweeted = 0;
	$('.tweet').each(function() {
		var div = $(this);
		div.css('display', 'none');
		if (div.data('tweet')) {
			$.get('/embedded/' + div.data('tweet'), function(res) {
				if (res['result'] !== undefined && res['result']) {
					div.html(res['html']);
				}
                                numtweeted++;
			});
		}
	});

        var check_tweet_count = function() {
            if (numtweeted >= numtweets) {
		$('#tweet-spinner').remove();
		twttr.widgets.load();
		$('.tweet').css('display', 'block');
                clearInterval(interval_id);
            }
        };
	var interval_id = window.setInterval(check_tweet_count, 1000);
};
					   

var generate_delegate_row = function(delegate) {
	var li = $('<li></li>');
        li.addClass('delegate-row');
	li.append('<span>' + delegate['user']['email'] + '</span>');
        if (!delegate['user']['activated']) {
            li.append('&nbsp;<span style="color: #CCCCCC;">(Invited)</span>');
        }
        li.append('&nbsp;');
	var anchor = $('<a href="#" class="delete-twitter-delegate button-link" data-delegate="' + delegate['id'] + '">Revoke</a>');
        var modchecked = (delegate['moderated'] === true) ? ' checked' : '';
        var moderatedcheck = $('<input' + modchecked + ' type="checkbox" class="moderated-checkbox" data-delegate="' + delegate['id'] + '" /> Moderated');
	li.append(anchor);
        var span = $('<span></span>');
        span.append(moderatedcheck);
        span.append($('<span> Moderated?</span>'));
        li.append(span);
        return li
};

var generate_delegate_rows = function(delegates) {
	var p = $('<p class="delegate-list-container"></p>');
	p.append('<h2>Delegates</h2>');
	var ul = $('<ul></ul>');
        ul.addClass('delegate-list');
	for(var del in delegates) {
		ul.append(generate_delegate_row(delegates[del]));
	}
	p.append(ul);
	return p;
}

var generate_delegates = function() {
	$('.delegate-section').each(function() {
		var row = $(this);
		$.get('/twitter-delegates/' + row.data('twitter'), function(result) {
			 if (result['result'] !== undefined && result['result'].length !== undefined) {
                            console.log('wang');
				var part = generate_delegate_rows(result['result']);
                            row.find('p.delegate-list-container').remove();
				row.append(part);
			 }
		});
	});
};

var judge_tweet = function(tweet) {
    tweet = tweet.replace(/http:\/\/[^ ]*/g, '01234567890123456789');
    tweet = tweet.replace(/https:\/\/[^ ]*/g, '012345678901234567890');
    return UNorm.nfc(tweet).length;
}

var add_to_recent = function(tweet_id) {
	$.get('/embedded/' + tweet_id, function(res) {
		if (res['result'] !== undefined && res['result']) {
			var tweetdiv = $('<div id="tweet-' + tweet_id + '" class="tweet" data-tweet="' + tweet_id + '"></div>');
			tweetdiv.html(res['html']);
			tweetdiv.css('display', 'none');
			$('#recent-tweets-inner').prepend(tweetdiv);
			window.setTimeout(function() {
				twttr.widgets.load();
				tweetdiv.css('display', 'block');
			}, 250);
		}
	});
};

$(document).ready(function() {

        $('#tweet').on('change keydown keyup', function() {
            var curcount = 140 - judge_tweet($(this).val());
            var curcolor;
            if (curcount > 20) {
                    curcolor = "#CCCCCC";
            } else if (curcount > 10) {
                    curcolor = "#770000";
            } else if (curcount > 1) {
                    curcolor = "#AA0000";
            } else {
                    curcolor = "#FF0000";
            }

            $('#tweet-length').text(curcount);
            $('#tweet-length').css('color', curcolor);
        });

        $('#tweet-form').on('submit', function() { return false; });
        
        $('#send-tweet').on('click', function() {
            var tweet_text = $('#tweet').val();
            if (judge_tweet(tweet_text) > 140) {
                return false;
            } else {
                var buttan = $(this);
                buttan.css('background-color', '#666666');
                buttan.css('color', '#555555');
                var token = $('#submission-token');
                var payload = {
                    tweet: tweet_text,
                    twitter_account_id: $('#twitter-account').val()
                };
                if (token !== undefined) payload['token'] = token.val();
                $.post('/send-tweet', payload, function(result) {
                    if (result['result'] === 'tweeted') {
                        flash('Tweet tweet!', 'success');
                        $('#tweet').val('');
                        add_to_recent(result['tweet_id']);
                    } else if (result['result'] == 'pending') {
                        flash('Your tweet is pending review.', 'success');
                        $('#tweet').val('');
                    } else {
                        flash('There was an error sending your tweet. Check it and try again.', 'error');
                    }
                    buttan.css('background-color', '#FFFFFF');
                    buttan.css('color', '#333333');
                });
            }
        });

	$('.delete-twitter').each(function() {
		var li = $(this).parent().parent();
		$(this).click(function() {
			var twitter_account_id = $(this).data('twitter');
			jConfirm("Are you sure?", "Confirmation", function() {
				$.post('/remove-twitter', {
					twitter_account_id: twitter_account_id
				}, function(res) {
					if (res['result']) {
						flash('Twitter account deleted.', 'success');
						$(li).remove();
					} else {
						flash('Twitter account was not deleted.', 'error');
					}
				});
			});
		});
	});

	$('.twitter-delegate-form').each(function() {
		var theform = $(this);
		theform.on('submit', function(e) {
			e.stopPropagation();
			var twitter_account_id = $(this).parent().data('twitter');
			$.post('/delegate-twitter', {
				"twitter_account_id": twitter_account_id,
				"email": theform.find('input[name="email"]').val()
			}, function(res) {
				if (res['result'] === 'delegated') {
					flash('Account was successfully delegated.', 'success');
				} else if (res['result'] === 'invited') {
					flash('User was invited to join fatnest. When they join their delegation will be active.', 'success');
				} else {
					flash('Could not delegate to that address. Check it and try again.', 'error');
					return;
				}
                                generate_delegates();
			});
			return false;
		});
	});

	$('.delete-twitter-delegate').live('click', function() {
		var button = $(this);
		jConfirm("Are you sure?", "Confirmation", function() {
			var delegate_id = button.data('delegate');
			$.post('/delete-twitter-delegate', {
				delegate: delegate_id
			}, function(res) {
				if (res['result']) {
					flash('Delegation revoked.', 'success');
					generate_delegates();
				} else {
					flash('Delegation could not be revoked.', 'error');
				}
			});
		});
	});

	$('#moderate-anonymous').live('change', function() {
		$.post('/set-anonymous-moderation', {
			twitter_account: $(this).data('twitter-id'),
			moderated: $(this).attr('checked') !== undefined && $(this).attr('checked')
		}, function() { // do nothing!
		});
	});


	$('.moderated-checkbox').live('change', function() {
		var delegate_id = $(this).data('delegate');
		$.post('/set-delegate-moderation', {
			delegate: delegate_id,
			moderated: $(this).attr('checked') !== undefined && $(this).attr('checked')
		}, function() { // do nothing!
		});
	});

	$('.reject-tweet').live('click', function() {
		var button = $(this);
		$.post('/reject-tweet', {
			tweet: button.data('tweet')
			}, function(res) {
				if (res['result']) {
					flash('Tweet rejected.');
					button.parent().remove();
				} else {
					flash('Could not reject tweet.');
				}
			}
		);
	});

	$('.approve-tweet').live('click', function() {
		var button = $(this);
		$.post('/approve-tweet', {
			tweet: button.data('tweet')
			}, function(res) {
				if (res['result']) {
					flash('Tweet approved.');
					button.parent().remove();
                                        add_to_recent(res['tweet_id']);
				} else {
					flash('Could not approve tweet.');
				}
			}
		);
	});
		

	generate_delegates();
	generate_embedded_tweets();
});
